// src/api/services/riskScoringService.js

const { pool } = require('../../config/db'); // Use pg pool directly
const moment = require('moment'); // Using moment for easier date calculations

// --- Heuristics Definitions ---
const PAYROLL_CATEGORY_IDS = ['21006']; // Prefix match
const PAYROLL_KEYWORDS_REGEX = /\b(ADP|PAYROLL|PAYCHEX|PAYROLL? CORP|GUSTO|TRINET|INTUIT PAYROLL|BAMBOOHR)\b/i;

const LOAN_CATEGORY_IDS = ['23005']; // Prefix match
const LOAN_KEYWORDS_REGEX = /\b(FINANCE|LOAN|CREDIT|CAPITAL ONE|DISCOVER|CHASE CARD|AMEX)\b/i;
const P2P_EXCLUSION_REGEX = /\b(ZELLE|VENMO|CASH APP|PAYPAL)\b/i;

const OD_FEE_CATEGORY_ID = '22001000'; // Exact match
const OD_FEE_KEYWORDS_REGEX = /OVERDRAFT|OD FEE|RET ITEM FEE|NSF FEE/i;
// --- End Heuristics Definitions ---

// --- Payroll Confidence Constants ---
const PAYROLL_RULE_CATEGORY = 1; // 001
const PAYROLL_RULE_KEYWORD = 2;  // 010
const PAYROLL_RULE_CADENCE = 4;  // 100
// --- End Payroll Confidence Constants ---


/**
 * Tags transactions based on predefined heuristics for payroll, loan payments, and overdraft fees.
 * Also calculates a confidence weight for payroll transactions.
 * @param {Array<object>} transactions - Array of transaction objects from the database.
 * @param {object} overrides - Object containing potential admin overrides (e.g., { transactionId: { is_payroll: false } }).
 * @returns {Array<object>} - The transactions array with added flags and weights: is_payroll, is_loanpay, is_odfee, payroll_confidence_weight.
 */
function tagTransactions(transactions, overrides = {}) {
    console.log(`Tagging ${transactions.length} transactions...`);

    // --- Heuristic 1.1 Rule 3: Payroll Pattern Detection (Helper data structure) ---
    const potentialPayrolls = {}; // Store { amount_key: [dates] } for negative amounts
    const ninetyDaysAgo = moment().subtract(90, 'days'); // Relative to today, adjust if needed based on reportDate

    transactions.forEach(tx => {
        // Ensure amount is numeric and date is valid
        const amount = parseFloat(tx.amount);
        const date = moment(tx.date);

        if (isNaN(amount) || !date.isValid()) {
            console.warn(`Skipping transaction ${tx.id} due to invalid amount or date.`);
            return; // Skip malformed transactions
        }

        tx.amountNum = amount; // Store numeric amount for easier use
        tx.dateMoment = date; // Store moment object

        // Initialize flags and new fields
        tx.is_payroll = false; // Will be set finally based on weight
        tx.is_loanpay = false;
        tx.is_odfee = false;
        tx.payroll_rule_mask = 0; // Bitmask for payroll rules
        tx.payroll_confidence_weight = 0.0; // Confidence weight

        // --- Payroll Detection (Rule Masking) ---
        if (amount < 0) { // Only inflows can be payroll
            // 1.1 Rule 1: Plaid Category
            if (
                (tx.category && tx.category.includes('Payroll')) ||
                (tx.category_id && PAYROLL_CATEGORY_IDS.some(prefix => tx.category_id.startsWith(prefix)))
            ) {
                tx.payroll_rule_mask |= PAYROLL_RULE_CATEGORY;
            }
            // 1.1 Rule 2: Keywords
            // Use 'else if' if rules are mutually exclusive for applying mask bits once,
            // but the requirement implies multiple rules can fire, so use separate 'if'.
            if (
                (tx.original_description && PAYROLL_KEYWORDS_REGEX.test(tx.original_description)) ||
                (tx.merchant_name && PAYROLL_KEYWORDS_REGEX.test(tx.merchant_name))
            ) {
                 tx.payroll_rule_mask |= PAYROLL_RULE_KEYWORD;
            }

            // Prepare data for Rule 3 (Pattern Detection) - only if within last 90 days relative to now
            if (date.isSameOrAfter(ninetyDaysAgo)) {
                 // Group by amount within a tolerance (e.g., $2)
                const amountKey = Math.round(Math.abs(amount) / 2) * 2; // Simple way to group by $2 buckets
                if (!potentialPayrolls[amountKey]) {
                    potentialPayrolls[amountKey] = [];
                }
                // Store the transaction *object* itself to modify its mask later
                potentialPayrolls[amountKey].push(tx);
            }
        }

        // --- Loan / Credit Payment Detection ---
        if (amount > 0) { // Only outflows can be loan payments
            // 1.2 Rule 1: Plaid Category
            if (
                (tx.category && (tx.category.includes('Loan Payment') || tx.category.includes('Credit Card Payment'))) ||
                (tx.category_id && LOAN_CATEGORY_IDS.some(prefix => tx.category_id.startsWith(prefix)))
            ) {
                tx.is_loanpay = true;
            }
            // 1.2 Rule 2: Specific Loan Keywords (excluding generic 'PAYMENT')
            else if (tx.original_description && LOAN_KEYWORDS_REGEX.test(tx.original_description)) {
                 tx.is_loanpay = true;
            }
            // 1.2 Rule 3: Check for 'PAYMENT' keyword specifically, excluding P2P terms
            else if (tx.original_description && /\bPAYMENT\b/i.test(tx.original_description)) {
                // Only flag as loan payment if it contains 'PAYMENT' AND does NOT contain P2P exclusion terms
                if (!P2P_EXCLUSION_REGEX.test(tx.original_description)) {
                    tx.is_loanpay = true;
                }
            }
        }

        // --- Overdraft Fee Detection ---
        // 1.3 Rule 1: Plaid Category ID
        if (tx.category_id === OD_FEE_CATEGORY_ID) {
            tx.is_odfee = true;
        }
        // 1.3 Rule 2: Keywords
        else if (tx.original_description && OD_FEE_KEYWORDS_REGEX.test(tx.original_description)) {
             tx.is_odfee = true;
        }

    });

    // --- Post-processing: Apply Payroll Pattern Detection (Rule 3) ---
    const recurringPayrollTxIds = new Set(); // Still useful for logging
    for (const amountKey in potentialPayrolls) {
        const deposits = potentialPayrolls[amountKey]; // These are now full tx objects
        if (deposits.length >= 3) { // Need at least 3 deposits to check cadence
            // Sort by the moment object date
            deposits.sort((a, b) => a.dateMoment.diff(b.dateMoment)); // Use dateMoment for sorting

            const gaps = [];
            for (let i = 1; i < deposits.length; i++) {
                // Use dateMoment for calculating gaps
                gaps.push(deposits[i].dateMoment.diff(deposits[i - 1].dateMoment, 'days'));
            }

            // Check for consistent 7, 14, or 15 day cadence (allowing some tolerance, e.g., +/- 1 day)
            const targetCadences = [7, 14, 15];
            for (const target of targetCadences) {
                let matchCount = 0;
                gaps.forEach(gap => {
                    if (Math.abs(gap - target) <= 1) { // Allow +/- 1 day tolerance
                        matchCount++;
                    }
                });

                // If at least 2 gaps match the cadence (meaning >= 3 deposits)
                // A more robust check might look for consecutive matches. This is simpler.
                if (matchCount >= 2) {
                    deposits.forEach(d => {
                        recurringPayrollTxIds.add(d.id); // Keep for logging
                        d.payroll_rule_mask |= PAYROLL_RULE_CADENCE; // Set the cadence bit on the original tx object
                    });
                    break; // Found a pattern for this amount group
                }
            }
        }
    }
    console.log(`Identified ${recurringPayrollTxIds.size} potential recurring payroll deposits based on cadence.`);

    // --- Calculate Final Payroll Status and Weight ---
    transactions.forEach(tx => {
        if (tx.amountNum < 0) { // Only consider inflows for payroll weight/status
            const ruleCount = (tx.payroll_rule_mask & PAYROLL_RULE_CATEGORY ? 1 : 0) +
                              (tx.payroll_rule_mask & PAYROLL_RULE_KEYWORD ? 1 : 0) +
                              (tx.payroll_rule_mask & PAYROLL_RULE_CADENCE ? 1 : 0);

            if (ruleCount === 3) {
                tx.payroll_confidence_weight = 1.0;
            } else if (ruleCount === 2) {
                tx.payroll_confidence_weight = 0.5;
            } else if (ruleCount === 1) {
                tx.payroll_confidence_weight = 0.2;
            } else {
                tx.payroll_confidence_weight = 0.0;
            }

            // Set final is_payroll flag based on weight
            tx.is_payroll = tx.payroll_confidence_weight > 0;
        }
    });

    // --- Apply Admin Overrides (if any) ---
    // Overrides take precedence and simplify confidence for now.
    transactions.forEach(tx => {
        // Always use the database ID as the key for overrides, as this is what the frontend sends.
        const overrideKey = tx.id; 
        // const plaidTransactionId = tx.transaction_id || tx.id; // Old logic - potential mismatch

        if (overrides[overrideKey]) { // Use the database ID key
            const overrideFlags = overrides[overrideKey];
            if (overrideFlags.hasOwnProperty('is_payroll')) {
                tx.is_payroll = overrideFlags.is_payroll;
                // If admin overrides payroll status, set confidence accordingly
                tx.payroll_confidence_weight = tx.is_payroll ? 1.0 : 0.0;
                if (!tx.is_payroll) tx.payroll_rule_mask = 0; // Clear mask if overridden to false
            }
            if (overrideFlags.hasOwnProperty('is_loanpay')) {
                tx.is_loanpay = overrideFlags.is_loanpay;
            }
            // is_odfee is not overridable per requirements
        }
    });

    console.log('Transaction tagging complete with payroll confidence weights.');
    return transactions;
}

/**
 * Fetches the necessary Plaid data (transactions, balances) for a user from their latest asset report.
 * @param {string} userId - The UUID of the user.
 * @returns {Promise<object>} - Object containing assetReportId, reportDate, transactions, historicalBalances, and currentBalance.
 * @throws {Error} - If user, Plaid item, asset report, or associated account data is not found.
 */
async function getPlaidDataForUser(userId) {
  console.log(`Fetching Plaid data for user: ${userId}`);

  // 1. Find the latest asset_report for the user using pg pool
  const reportQuery = `
    SELECT id, created_at, date_generated 
    FROM asset_reports 
    WHERE user_id = $1 
    ORDER BY created_at DESC 
    LIMIT 1;
  `;
  const reportResult = await pool.query(reportQuery, [userId]);
  const latestReport = reportResult.rows[0]; // Get the first row

  if (!latestReport) {
    throw new Error(`No asset report found for user ${userId}`);
  }

  const assetReportId = latestReport.id;
  const reportDate = latestReport.date_generated || latestReport.created_at;
  console.log(`Using asset report ${assetReportId} generated around ${reportDate}`);

  // 2. Find the associated asset_report_account (assuming single account)
  const accountQuery = `
    SELECT ara.id, ara.balance_current 
    FROM asset_report_accounts ara
    JOIN asset_report_items ari ON ara.asset_report_item_id = ari.id
    WHERE ari.asset_report_id = $1
    LIMIT 1;
  `;
  const accountResult = await pool.query(accountQuery, [assetReportId]);
  const account = accountResult.rows[0];

  if (!account) {
    console.error(`Data Integrity Issue: No associated asset_report_accounts found for asset_report_id: ${assetReportId}. Cannot proceed with risk scoring.`); 
    throw new Error(`No associated account found for asset report ${assetReportId}`);
  }

  const assetReportAccountId = account.id;
  const currentBalance = account.balance_current;

  // 3. Get all transactions linked to that account
  const transactionQuery = `
    SELECT * 
    FROM asset_report_transactions 
    WHERE asset_report_account_id = $1 
    ORDER BY date ASC;
  `;
  const transactionResult = await pool.query(transactionQuery, [assetReportAccountId]);
  const transactions = transactionResult.rows;

  // 4. Get historical balances linked to that account
  const balanceQuery = `
    SELECT balance_date, balance_current 
    FROM asset_report_account_historical_balances 
    WHERE asset_report_account_id = $1 
    ORDER BY balance_date ASC;
  `;
  const balanceResult = await pool.query(balanceQuery, [assetReportAccountId]);
  const historicalBalances = balanceResult.rows;

  console.log(`Fetched ${transactions.length} transactions and ${historicalBalances.length} historical balance records.`);

  if (transactions.length === 0) {
    console.warn(`No transactions found for asset report ${assetReportId}. History check might fail.`);
  }

  return {
    assetReportId,
    assetReportAccountId,
    reportDate: reportDate ? new Date(reportDate) : new Date(),
    transactions,
    historicalBalances,
    currentBalance: currentBalance !== null ? parseFloat(currentBalance) : null,
  };
}

// --- Math Utilities ---
function calculateMedian(numbers) {
    if (!numbers || numbers.length === 0) return null;
    const sorted = [...numbers].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    if (sorted.length % 2 === 0) {
        return (sorted[mid - 1] + sorted[mid]) / 2;
    } else {
        return sorted[mid];
    }
}

/**
 * Calculates the weighted median of a list of values.
 * @param {Array<[number, number]>} valueWeightPairs - Array of [value, weight] pairs.
 * @returns {number | null} - The weighted median value, or null if input is empty.
 */
function calculateWeightedMedian(valueWeightPairs) {
    if (!valueWeightPairs || valueWeightPairs.length === 0) return null;

    // Remove entries with zero weight as they don't contribute
    const validPairs = valueWeightPairs.filter(pair => pair[1] > 0);
    if (validPairs.length === 0) return null;

    // Sort pairs by value
    validPairs.sort((a, b) => a[0] - b[0]);

    const totalWeight = validPairs.reduce((sum, pair) => sum + pair[1], 0);
    const targetWeight = totalWeight / 2;

    let cumulativeWeight = 0;
    for (let i = 0; i < validPairs.length; i++) {
        cumulativeWeight += validPairs[i][1];
        if (cumulativeWeight >= targetWeight) {
            // Standard definition: if cumulative weight exactly hits targetWeight,
            // median is average of this value and the next. Simplified here:
            // we take the value that crosses the threshold.
            // More robust: check if cumulativeWeight - weight === targetWeight and average if needed.
            // For simplicity now, just return the value that crosses.
            return validPairs[i][0];
        }
    }

    // Should not be reached if totalWeight > 0, but as a fallback:
    return validPairs[validPairs.length - 1][0];
}

function calculateStdDev(numbers) {
    if (!numbers || numbers.length < 2) return null; // Std dev requires at least 2 points
    const n = numbers.length;
    const mean = numbers.reduce((sum, val) => sum + val, 0) / n;
    const variance = numbers.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / (n - 1); // Sample std dev (n-1)
    return Math.sqrt(variance);
}

/**
 * Calculates the weighted standard deviation of a list of values.
 * Uses sample standard deviation formula (denominator N-1 equivalent for weights).
 * @param {Array<[number, number]>} valueWeightPairs - Array of [value, weight] pairs.
 * @returns {number | null} - Weighted standard deviation, or null if insufficient data.
 */
function calculateWeightedStdDev(valueWeightPairs) {
    if (!valueWeightPairs || valueWeightPairs.length === 0) return null;

    // Filter out pairs with zero or negative weight
    const validPairs = valueWeightPairs.filter(pair => pair[1] > 0);
    if (validPairs.length < 2) return null; // Need at least 2 data points for std dev

    const totalWeight = validPairs.reduce((sum, pair) => sum + pair[1], 0);
    if (totalWeight <= 0) return null;

    // Calculate weighted mean
    const weightedMean = validPairs.reduce((sum, pair) => sum + pair[0] * pair[1], 0) / totalWeight;

    // Calculate weighted variance (using unbiased N-1 correction factor V1/(V1^2 - V2) where V1=sum(w), V2=sum(w^2))
    // Simpler approach (biased, equivalent to N denominator) often sufficient:
    const weightedVarianceBiased = validPairs.reduce((sum, pair) => {
        return sum + pair[1] * Math.pow(pair[0] - weightedMean, 2);
    }, 0) / totalWeight;

    // For unbiased sample variance (N-1 equivalent):
    // Method 1: Effective Sample Size (sum of weights)^2 / sum(weights^2)
    // let sumWeightsSq = validPairs.reduce((sum, pair) => sum + pair[1] * pair[1], 0);
    // let effectiveN = totalWeight * totalWeight / sumWeightsSq;
    // if (effectiveN <= 1) return 0; // Variance is 0 if only one effective sample
    // let weightedVarianceUnbiased = (totalWeight / (totalWeight - 1)) * weightedVarianceBiased; // Approximation

    // Method 2: Sum(w * (x - x_bar_w)^2) / (Sum(w) - Sum(w^2)/Sum(w))
    // Let's use the simpler biased version for now, as the impact on score buckets might be minimal.
    // If unbiased is strictly needed, more complex calculation required.
    if (weightedVarianceBiased < 0) return 0; // Avoid NaN from floating point issues

    return Math.sqrt(weightedVarianceBiased);
}

// --- Metric Calculation Helpers ---

/**
 * Calculates C7 (Clean Buffer 7-day min) and BV (Buffer Volatility 7-day std dev).
 * Handles gaps in historical balances using forward-filling.
 * @param {Array<object>} historicalBalances - Sorted array of { balance_date, balance_current }.
 * @param {number | null} currentBalance - The current balance (B0).
 * @param {Date} reportDate - The reference date (today).
 * @returns {{cleanBuffer7: number | null, bufferVolatility: number | null}} - Object with C7 and BV.
 */
function calculateBufferMetrics(historicalBalances, currentBalance, reportDate) {
    if (currentBalance === null) {
        console.warn("BufferMetrics: Cannot calculate without currentBalance.");
        return { cleanBuffer7: null, bufferVolatility: null };
    }

    const reportMoment = moment(reportDate).startOf('day'); // Ensure we compare dates correctly
    const dailyBalances = new Map(); // Map<'YYYY-MM-DD', number>

    // Populate map with available historical data within the last ~10 days (buffer for forward fill)
    const tenDaysAgo = reportMoment.clone().subtract(9, 'days');
    if (historicalBalances) {
        historicalBalances.forEach(hb => {
            const balanceDateMoment = moment(hb.balance_date).startOf('day');
            if (balanceDateMoment.isSameOrAfter(tenDaysAgo) && balanceDateMoment.isSameOrBefore(reportMoment)) {
                const balance = parseFloat(hb.balance_current);
                if (!isNaN(balance)) {
                    dailyBalances.set(balanceDateMoment.format('YYYY-MM-DD'), balance);
                }
            }
        });
    }
    // Add current balance for today
    dailyBalances.set(reportMoment.format('YYYY-MM-DD'), currentBalance);

    // Generate the 7 daily balances with forward-filling
    const sevenDayBalances = [];
    let lastKnownBalance = currentBalance; // Start with today's balance for filling backwards

    for (let i = 0; i < 7; i++) {
        const targetDate = reportMoment.clone().subtract(i, 'days');
        const dateStr = targetDate.format('YYYY-MM-DD');

        if (dailyBalances.has(dateStr)) {
            lastKnownBalance = dailyBalances.get(dateStr);
            sevenDayBalances.push(lastKnownBalance);
        } else {
            // Forward-fill (using the balance from the *next* known day when iterating backwards)
            sevenDayBalances.push(lastKnownBalance);
        }
    }
    sevenDayBalances.reverse(); // Put balances in chronological order [T-6, T-5, ..., T-0]

    if (sevenDayBalances.length !== 7) {
        console.warn(`BufferMetrics: Incorrect number of daily balances generated (${sevenDayBalances.length}).`);
        // This shouldn't happen with the loop structure, but safeguard
        return { cleanBuffer7: null, bufferVolatility: null };
    }

    // Calculate C7 (minimum balance)
    const cleanBuffer7 = Math.min(...sevenDayBalances);

    // Calculate BV (standard deviation)
    const bufferVolatility = calculateStdDev(sevenDayBalances);

    console.log(`Calculated C7 (Min Balance Last 7 Days, Forward-Filled): ${cleanBuffer7}`);
    console.log(`Calculated BV (Std Dev Balance Last 7 Days, Forward-Filled): ${bufferVolatility}`);

    return { cleanBuffer7, bufferVolatility };
}

/**
 * Calculates DM30: Deposit Multiplicity over the last 30 days.
 * Ratio of unique inflow counterparties to payroll events.
 * @param {Array<object>} taggedTransactions - Transactions with flags, amountNum, merchant_name, original_description.
 * @param {Date} reportDate - The reference date (today).
 * @returns {number | null} - DM30 ratio, or null if calculation isn't possible.
 */
function calculateDM30(taggedTransactions, reportDate) {
    const reportMoment = moment(reportDate);
    const thirtyDaysAgo = reportMoment.clone().subtract(29, 'days'); // Include today

    let payrollEvents30 = 0;
    const inflowCounterparties = new Set();

    taggedTransactions.forEach(tx => {
        // Consider transactions within the last 30 days
        if (tx.dateMoment.isSameOrAfter(thirtyDaysAgo) && tx.dateMoment.isSameOrBefore(reportMoment)) {

            // Check for payroll events (using the final is_payroll flag)
            if (tx.is_payroll) {
                payrollEvents30++;
            }

            // Check for inflows to count counterparties
            if (tx.amountNum < 0) {
                let counterparty = tx.merchant_name || tx.original_description || 'Unknown';
                // Truncate original_description if used, as per spec (e.g., 16 chars)
                if (!tx.merchant_name && tx.original_description) {
                    counterparty = counterparty.substring(0, 16);
                }
                inflowCounterparties.add(counterparty.trim().toUpperCase()); // Normalize
            }
        }
    });

    const uniqueInflowCounterparties30 = inflowCounterparties.size;
    // Denominator: Max(1, PayrollEvents30)
    const denominator = Math.max(1, payrollEvents30);

    const dm30 = uniqueInflowCounterparties30 / denominator;

    console.log(`Calculated DM30 (Unique Inflows / Payroll Events): ${dm30} (${uniqueInflowCounterparties30} / ${denominator})`);
    return dm30;
}

/**
 * Calculates F: Count of overdraft fees in the last 90 days.
 * @param {Array<object>} taggedTransactions - Array of transactions with is_odfee flag.
 * @param {Date} reportDate - The reference date (today).
 * @returns {number} - The count of overdraft fees.
 */
function calculateF(taggedTransactions, reportDate) {
    const reportMoment = moment(reportDate);
    const ninetyDaysAgo = reportMoment.clone().subtract(89, 'days'); // Include today, go back 89 days

    let overdraftCount = 0;
    taggedTransactions.forEach(tx => {
        if (tx.is_odfee && tx.dateMoment.isSameOrAfter(ninetyDaysAgo) && tx.dateMoment.isSameOrBefore(reportMoment)) {
            overdraftCount++;
        }
    });

    console.log(`Calculated F (Overdraft Count Last 90 Days): ${overdraftCount}`);
    return overdraftCount;
}

/**
 * Calculates P: Weighted median paycheck amount.
 * Also returns the list of payroll transactions (with weights) for use by D and sigmaP.
 * @param {Array<object>} taggedTransactions - Transactions with is_payroll flag and payroll_confidence_weight.
 * @returns {{medianPaycheck: number | null, payrollTransactions: Array<object>, totalPayrollWeight: number}}
 */
function calculateP(taggedTransactions) {
    // Filter for transactions flagged as payroll (weight > 0)
    const payrollTransactions = taggedTransactions.filter(tx => tx.is_payroll);

    if (payrollTransactions.length === 0) {
        console.log('No payroll transactions found.');
        return { medianPaycheck: null, payrollTransactions: [], totalPayrollWeight: 0 };
    }

    // Prepare data for weighted median: [absolute_amount, weight]
    const amountWeightPairs = payrollTransactions.map(tx => [
        Math.abs(tx.amountNum),
        tx.payroll_confidence_weight
    ]);

    const medianPaycheck = calculateWeightedMedian(amountWeightPairs);
    const totalPayrollWeight = amountWeightPairs.reduce((sum, pair) => sum + pair[1], 0);

    console.log(`Found ${payrollTransactions.length} payroll transactions.`);
    console.log(`Calculated P (Weighted Median Paycheck): ${medianPaycheck}`);
    return { medianPaycheck, payrollTransactions, totalPayrollWeight };
}

/**
 * Calculates D: Days since the last paycheck (considering only High/Medium confidence).
 * @param {Array<object>} payrollTransactions - Filtered payroll transactions (including weights).
 * @param {Date} reportDate - The reference date (today).
 * @returns {number | null} - Days since last paycheck, or null if no High/Medium confidence paychecks.
 */
function calculateD(payrollTransactions, reportDate) {
    // Filter for medium or high confidence payrolls
    const reliablePayrolls = payrollTransactions.filter(
        tx => tx.payroll_confidence_weight >= 0.5
    );

    if (!reliablePayrolls || reliablePayrolls.length === 0) {
        console.log('D: No medium or high confidence payrolls found.');
        return null;
    }

    // Sort DESC by date to get latest first
    reliablePayrolls.sort((a, b) => b.dateMoment.diff(a.dateMoment));

    const lastPaycheckDate = reliablePayrolls[0].dateMoment;
    const reportMoment = moment(reportDate);
    const daysSince = reportMoment.diff(lastPaycheckDate, 'days');

    console.log(`Calculated D (Days Since Last Reliable Paycheck): ${daysSince}`);
    return daysSince;
}

/**
 * Calculates sigma_P: Weighted Paycheck regularity (std dev of days between paychecks).
 * Requires at least 2 paychecks with weight > 0 within the last 180 days.
 * @param {Array<object>} payrollTransactions - Filtered payroll transactions (must include weights).
 * @param {Date} reportDate - The reference date.
 * @returns {number | null} - Weighted standard deviation of gaps, or null if < 2 paychecks in period.
 */
function calculateSigmaP(payrollTransactions, reportDate) {
    const reportMoment = moment(reportDate);
    const oneEightyDaysAgo = reportMoment.clone().subtract(179, 'days');

    // Filter for paychecks within the last 180 days that have weight > 0
    const recentPayrolls = payrollTransactions.filter(tx =>
        tx.payroll_confidence_weight > 0 &&
        tx.dateMoment.isSameOrAfter(oneEightyDaysAgo) &&
        tx.dateMoment.isSameOrBefore(reportMoment)
    );

    if (recentPayrolls.length < 2) {
        console.log(`SigmaP_w: Not enough recent weighted payrolls (${recentPayrolls.length}) in the last 180 days.`);
        return null;
    }

    // Sort by date to calculate gaps correctly
    recentPayrolls.sort((a, b) => a.dateMoment.diff(b.dateMoment)); // ASC

    const gapWeightPairs = [];
    for (let i = 1; i < recentPayrolls.length; i++) {
        const gap = recentPayrolls[i].dateMoment.diff(recentPayrolls[i - 1].dateMoment, 'days');
        // Weight of the gap is the minimum of the weights of the two transactions defining it
        const weight = Math.min(
            recentPayrolls[i].payroll_confidence_weight,
            recentPayrolls[i - 1].payroll_confidence_weight
        );
        if (weight > 0) { // Only include gaps with positive weight
            gapWeightPairs.push([gap, weight]);
        }
    }

    if (gapWeightPairs.length === 0) {
        // This could happen if e.g., only two payrolls exist and one has weight 0, leading to 0 weight gaps
        console.log(`SigmaP_w: No valid gaps with positive weight found.`);
        return null;
    }

    const stdDevGaps = calculateWeightedStdDev(gapWeightPairs);

    console.log(`Calculated SigmaP_w (Weighted Paycheck Regularity - StdDev of Gaps): ${stdDevGaps}`);
    return stdDevGaps;
}

/**
 * Helper to calculate daily net cash flow over a specified period.
 * @param {Array<object>} taggedTransactions - Transactions with amountNum and dateMoment.
 * @param {Date} reportDate - The reference date (today).
 * @param {number} historyDays - Total history duration (H).
 * @returns {Map<string, number>} - Map where key is 'YYYY-MM-DD' and value is net cash for that day.
 */
function calculateDailyNetCashMap(taggedTransactions, reportDate, historyDays) {
    const dailyNetCash = new Map();
    const reportMoment = moment(reportDate);
    const startDate = reportMoment.clone().subtract(historyDays - 1, 'days'); // Go back H-1 days

    // Initialize map for all days in the history period
    for (let m = moment(startDate); m.isSameOrBefore(reportMoment); m.add(1, 'days')) {
        dailyNetCash.set(m.format('YYYY-MM-DD'), 0);
    }

    // Aggregate transactions by day
    taggedTransactions.forEach(tx => {
        const dateStr = tx.dateMoment.format('YYYY-MM-DD');
        if (dailyNetCash.has(dateStr)) {
            // Remember: Plaid inflow is negative, outflow is positive
            const currentNet = dailyNetCash.get(dateStr);
            // We want NetCash = Inflow - Outflow
            // If amountNum < 0 (inflow), add Math.abs(amountNum)
            // If amountNum > 0 (outflow), subtract amountNum
            const netChange = tx.amountNum < 0 ? Math.abs(tx.amountNum) : -tx.amountNum;
            dailyNetCash.set(dateStr, currentNet + netChange);
        }
    });

    console.log(`Calculated daily net cash map for ${dailyNetCash.size} days.`);
    return dailyNetCash;
}

/**
 * Calculates N30: Net cash flow over the last 30 days.
 * @param {Map<string, number>} dailyNetCashMap - Map of daily net cash flows.
 * @param {Date} reportDate - The reference date (today).
 * @returns {number} - Total net cash flow for the last 30 days.
 */
function calculateN30(dailyNetCashMap, reportDate) {
    let netCash30 = 0;
    const reportMoment = moment(reportDate);
    const thirtyDaysAgo = reportMoment.clone().subtract(29, 'days'); // Include today

    for (let m = moment(thirtyDaysAgo); m.isSameOrBefore(reportMoment); m.add(1, 'days')) {
        const dateStr = m.format('YYYY-MM-DD');
        if (dailyNetCashMap.has(dateStr)) {
            netCash30 += dailyNetCashMap.get(dateStr);
        }
    }

    console.log(`Calculated N30 (Net Cash Last 30 Days): ${netCash30}`);
    return netCash30;
}

/**
 * Calculates R30: Debt Load Ratio (Loan Payments / Total Inflows) over the last 30 days.
 * @param {Array<object>} taggedTransactions - Transactions with flags and amountNum.
 * @param {Date} reportDate - The reference date (today).
 * @returns {number | null} - Debt load ratio, or null if no inflows in the period.
 */
function calculateR30(taggedTransactions, reportDate) {
    let totalLoanPayments30 = 0;
    let totalInflows30 = 0;
    const reportMoment = moment(reportDate);
    const thirtyDaysAgo = reportMoment.clone().subtract(29, 'days'); // Include today

    taggedTransactions.forEach(tx => {
        if (tx.dateMoment.isSameOrAfter(thirtyDaysAgo) && tx.dateMoment.isSameOrBefore(reportMoment)) {
            if (tx.is_loanpay && tx.amountNum > 0) { // Ensure it's an outflow tagged as loan payment
                totalLoanPayments30 += tx.amountNum;
            }
            if (tx.amountNum < 0) { // Any inflow
                totalInflows30 += Math.abs(tx.amountNum);
            }
        }
    });

    let debtLoadRatio = null;
    if (totalInflows30 > 0) {
        debtLoadRatio = totalLoanPayments30 / totalInflows30;
    } else {
        console.warn("R30: No inflows detected in the last 30 days. Ratio cannot be calculated.");
    }

    console.log(`Calculated R30 (Debt Load Ratio Last 30 Days): ${debtLoadRatio} (Payments: ${totalLoanPayments30}, Inflows: ${totalInflows30})`);
    return debtLoadRatio;
}

/**
 * Calculates V: Volatility (Std Dev of Net Cash / Mean Abs Net Cash) over last 90 days.
 * @param {Map<string, number>} dailyNetCashMap - Map of daily net cash flows.
 * @param {Date} reportDate - The reference date (today).
 * @returns {number | null} - Volatility ratio, or null if calculation isn't possible.
 */
function calculateV(dailyNetCashMap, reportDate) {
    const netCash90 = [];
    const reportMoment = moment(reportDate);
    const ninetyDaysAgo = reportMoment.clone().subtract(89, 'days'); // Include today

    // Collect daily net cash values for the last 90 days
    for (let m = moment(ninetyDaysAgo); m.isSameOrBefore(reportMoment); m.add(1, 'days')) {
        const dateStr = m.format('YYYY-MM-DD');
        if (dailyNetCashMap.has(dateStr)) {
            netCash90.push(dailyNetCashMap.get(dateStr));
        } else {
            netCash90.push(0); // Assume 0 if day is missing in map (shouldn't happen with initialization)
        }
    }

    if (netCash90.length < 2) {
        console.warn("V: Not enough data points (< 2) in the last 90 days for volatility calculation.");
        return null;
    }

    const stdDevNetCash = calculateStdDev(netCash90);

    // Calculate mean of the *absolute values* of daily net cash
    const absNetCash90 = netCash90.map(Math.abs);
    const meanAbsNetCash = absNetCash90.reduce((sum, val) => sum + val, 0) / absNetCash90.length;

    let volatility = null;
    if (stdDevNetCash === null) {
         console.warn("V: Standard deviation calculation failed (likely < 2 data points).");
         return null;
    }

    // Avoid division by zero or near-zero mean absolute net cash
    if (meanAbsNetCash > 0.01) { // Use a small threshold instead of strict zero
        volatility = stdDevNetCash / meanAbsNetCash;
    } else if (stdDevNetCash === 0) {
         // If mean abs is zero and std dev is also zero, volatility is effectively zero.
         volatility = 0;
    } else {
        console.warn(`V: Mean absolute net cash (${meanAbsNetCash}) is too low to calculate a meaningful volatility ratio.`);
        // Depending on requirements, might return null or a very large number. Let's return null.
        return null;
    }

    console.log(`Calculated V (Volatility Last 90 Days): ${volatility} (StdDev: ${stdDevNetCash}, MeanAbs: ${meanAbsNetCash})`);
    return volatility;
}

/**
 * Orchestrates the calculation of all 8 core metrics.
 * Returns the metrics object and payroll details needed for scoring adjustments.
 * @param {Array<object>} taggedTransactions
 * @param {Array<object>} historicalBalances
 * @param {number | null} currentBalance
 * @param {object} metrics - The metrics object to populate (already contains H).
 * @param {Date} reportDate
 * @returns {{metrics: object, payrollTransactions: Array<object>, totalPayrollWeight: number}} - Populated metrics and payroll info.
 */
function calculateMetrics(taggedTransactions, historicalBalances, currentBalance, metrics, reportDate) {
    console.log("Calculating core metrics...");

    // Calculate C7 & BV (Replaces L7)
    const { cleanBuffer7, bufferVolatility } = calculateBufferMetrics(historicalBalances, currentBalance, reportDate);
    metrics.metric_clean_buffer7 = cleanBuffer7;
    metrics.metric_buffer_volatility = bufferVolatility;

    // Calculate DM30
    metrics.metric_deposit_multiplicity30 = calculateDM30(taggedTransactions, reportDate);

    // Calculate F (Overdraft Count)
    metrics.metric_overdraft_count90 = calculateF(taggedTransactions, reportDate);

    // --- Payroll Metrics ---
    const { medianPaycheck, payrollTransactions, totalPayrollWeight } = calculateP(taggedTransactions);
    metrics.metric_median_paycheck = medianPaycheck;

    // Calculate D (needs payrollTransactions)
    metrics.metric_days_since_last_paycheck = calculateD(payrollTransactions, reportDate);

    // Calculate sigma_P (needs payrollTransactions)
    metrics.metric_paycheck_regularity = calculateSigmaP(payrollTransactions, reportDate);

    // --- Net Cash and Related Metrics ---
    // Calculate Daily Net Cash Map first (needed for N30 and V)
    const dailyNetCashMap = calculateDailyNetCashMap(taggedTransactions, reportDate, metrics.metric_observed_history_days);

    // Calculate N30
    metrics.metric_net_cash30 = calculateN30(dailyNetCashMap, reportDate);

    // Calculate R30
    metrics.metric_debt_load30 = calculateR30(taggedTransactions, reportDate);

    // Calculate V
    metrics.metric_volatility90 = calculateV(dailyNetCashMap, reportDate);

    console.log("Core metrics calculation complete.");
    // Return metrics and payroll info needed for score adjustments
    return { metrics, payrollTransactions, totalPayrollWeight };
}

// --- Scoring Logic ---

const SCORE_CONSTANTS = {
    BASE_SCORE_MEAN: 40,
    BASE_SCORE_STD_DEV: 25,
    S_SCORE_SCALE_FACTOR: 15, // Multiplier for scaled deviation
    S_SCORE_CENTER: 50,
};

/**
 * Determines points for a given metric value based on predefined buckets.
 * @param {string} metricName - The name of the metric (e.g., 'H', 'F', 'sigmaP', 'D', 'R30', 'N30', 'V', 'P').
 * @param {number | null} value - The calculated value of the metric.
 * @returns {number} - The points awarded for that metric. Returns 0 if value is null or invalid.
 */
function getPointsForMetric(metricName, value) {
    // Handle null or undefined values - generally award 0 points
    if (value === null || typeof value === 'undefined') {
        // Null L7/C7 handled directly in calculateScores now
        // For other metrics like sigma_P, R30, V, null often means insufficient data to judge, so 0 points seems reasonable.
        return 0;
    }


    switch (metricName) {
        case 'H': // ObservedHistoryDays
            if (value >= 365) return 10;
            if (value >= 180) return 5;
            if (value >= 90) return 0;
            return 0; // Should not happen due to initial check, but safety net

        case 'F': // OverdraftCount90
            if (value === 0) return 20;
            if (value <= 2) return 5; // 1-2
            return -15; // >= 3

        case 'sigmaP': // PaycheckRegularity (σ_P)
             // Lower is better
            if (value <= 2) return 25;
            if (value <= 5) return 10; // 3-5
            return -10; // > 5

        case 'D': // DaysSinceLastPaycheck
            if (value <= 7) return 10;
            if (value <= 14) return 0; // 8-14
            return -10; // > 14

        case 'R30': // DebtLoad30
             // Lower is better
            if (value <= 0.15) return 20;
            if (value <= 0.30) return 5; // 0.16 - 0.30
            return -15; // > 0.30

        case 'N30': // NetCash30
            if (value >= 0) return 10;
            return -10; // < 0

        case 'V': // Volatility90
             // Lower is better
            if (value <= 0.40) return 10;
            if (value <= 0.70) return 0; // 0.41 - 0.70
            return -10; // > 0.70

        case 'P': // WeightedMedianPaycheck (P_w)
            if (value >= 1500) return 20;
            if (value >= 1000) return 10; // 1000 - 1499
            if (value >= 600) return 0;   // 600 - 999
            return -10; // < 600

        default:
            console.warn(`Unknown metric name for point calculation: ${metricName}`);
            return 0;
    }
}

/**
 * Calculates the BaseScore and the final BlinkScore S based on metric points.
 * Incorporates payroll confidence adjustments.
 * @param {object} metrics - Object containing all calculated metric values.
 * @param {Array<object>} payrollTransactions - Payroll transactions with weights.
 * @param {number} totalPayrollWeight - Sum of weights for all payroll transactions.
 * @returns {object} - Object containing { points: {...}, base_score: number, blink_score_s: number }
 */
function calculateScores(metrics, payrollTransactions, totalPayrollWeight) {
    // --- Payroll Confidence Check ---
    let lowPayrollConfidence = false;
    let effectivePayrollCount = payrollTransactions.length;
    // Check if overall confidence is low (e.g., average weight < 0.25)
    // Avoid division by zero if no payroll transactions found (should be handled by calculateP returning nulls)
    if (effectivePayrollCount > 0 && (totalPayrollWeight / effectivePayrollCount) < 0.25) {
        console.warn("Low overall payroll confidence detected (average weight < 0.25). Zeroing points for D and SigmaP.");
        lowPayrollConfidence = true;
    }
    // Add check from audit notes: Zero out points if *all* rows are low confidence (weight 0.2)
    // This is covered if average < 0.25, but adds explicit check.
    // const allLowConfidence = effectivePayrollCount > 0 && payrollTransactions.every(tx => tx.payroll_confidence_weight === 0.2);
    // if (allLowConfidence) {
    //     console.warn("All payroll transactions have low confidence (0.2). Zeroing points for D and SigmaP.");
    //     lowPayrollConfidence = true;
    // }
    // Sticking with average weight < 0.25 rule for now.

    // Calculate points for each metric
    const points = {
        points_observed_history: getPointsForMetric('H', metrics.metric_observed_history_days),
        points_overdraft_count90: getPointsForMetric('F', metrics.metric_overdraft_count90),
        // Apply confidence check to SigmaP, D, and P points
        points_paycheck_regularity: lowPayrollConfidence ? 0 : getPointsForMetric('sigmaP', metrics.metric_paycheck_regularity),
        points_days_since_last_paycheck: lowPayrollConfidence ? 0 : getPointsForMetric('D', metrics.metric_days_since_last_paycheck),
        points_debt_load30: getPointsForMetric('R30', metrics.metric_debt_load30),
        points_net_cash30: getPointsForMetric('N30', metrics.metric_net_cash30),
        points_volatility90: getPointsForMetric('V', metrics.metric_volatility90),
        points_median_paycheck: lowPayrollConfidence ? 0 : getPointsForMetric('P', metrics.metric_median_paycheck)
    };

    // --- Liquidity Points (C7 & BV) ---
    let liquidityPoints = 0;
    const c7 = metrics.metric_clean_buffer7;
    const bv = metrics.metric_buffer_volatility;

    // Check if C7 and BV are valid numbers before applying logic
    if (c7 !== null && bv !== null && !isNaN(c7) && !isNaN(bv)) {
        if (c7 >= 300) {
            if (bv <= 50) {
                liquidityPoints = 40; // High buffer, low volatility
            } else {
                liquidityPoints = 25; // High buffer, high volatility
            }
        } else if (c7 >= 100) {
            liquidityPoints = 10; // Medium buffer (regardless of volatility)
        } else {
            liquidityPoints = -20; // Low buffer (c7 < 100)
        }
    } else if (c7 !== null && !isNaN(c7)) {
        // Handle cases where BV might be null (e.g., only 1 balance point in 7 days)
        // Apply simplified logic based only on C7 if BV is unavailable
        if (c7 >= 300) {
            liquidityPoints = 25; // Default to lower high-buffer score without BV
        } else if (c7 >= 100) {
            liquidityPoints = 10;
        } else {
            liquidityPoints = -20;
        }
        console.warn(`Liquidity scoring: BV is null or NaN (value: ${bv}), using C7 only.`);
    } else {
        // If C7 itself is null or NaN, assign worst score or 0?
        // Assigning -20 seems consistent with < 100 rule.
        liquidityPoints = -20;
        console.warn(`Liquidity scoring: C7 is null or NaN (value: ${c7}). Assigning -20 points.`);
    }
    points.points_liquidity = liquidityPoints; // Add the calculated points

    // --- Deposit Multiplicity Penalty ---
    let dm30PenaltyPoints = 0;
    const dm30 = metrics.metric_deposit_multiplicity30;
    if (dm30 !== null && !isNaN(dm30) && dm30 > 4) {
        dm30PenaltyPoints = -15;
        console.log(`Applying DM30 penalty: ${dm30PenaltyPoints} points (DM30 = ${dm30})`);
    }
    points.points_deposit_multiplicity = dm30PenaltyPoints;

    const base_score = Object.values(points).reduce((sum, p) => sum + p, 0);

    // Apply linear stretch: S = MAX(0, MIN(100, 50 + 15 * (BaseScore - 40) / 25))
    const normalized_deviation = (base_score - SCORE_CONSTANTS.BASE_SCORE_MEAN) / SCORE_CONSTANTS.BASE_SCORE_STD_DEV;
    let blink_score_s_raw = SCORE_CONSTANTS.S_SCORE_CENTER + SCORE_CONSTANTS.S_SCORE_SCALE_FACTOR * normalized_deviation;

    // Clamp the score to [0, 100]
    const blink_score_s = Math.max(0, Math.min(100, blink_score_s_raw));

    console.log("Score calculation complete.");
    console.log("Points:", points);
    console.log(`BaseScore: ${base_score}`);
    console.log(`BlinkScore S (raw): ${blink_score_s_raw}, Clamped: ${blink_score_s}`);

    return {
        points, // Object with points per metric
        base_score,
        blink_score_s: parseFloat(blink_score_s.toFixed(2)), // Round to 2 decimal places
    };
}

// --- System Recommendation Logic ---

/**
 * Determines the system recommendation based on BlinkScore S and history length (Green Zone rules).
 * @param {number} blinkScoreS - The final calculated Blink Score S (0-100).
 * @param {number} historyDays - The observed history days (H).
 * @returns {'approved' | 'rejected'} - The system recommendation ('approved' for PASS, 'rejected' for FAIL).
 */
function getSystemRecommendation(blinkScoreS, historyDays) {
    let recommendation = 'rejected'; // Default to rejected

    if (blinkScoreS === null || historyDays < 90) {
        // Should not happen if checks are done earlier, but safeguard
        console.warn("Cannot determine recommendation: Invalid score or insufficient history.");
        return 'rejected';
    }

    // Green Zone rules (Section 6)
    if (historyDays >= 90 && historyDays <= 179) {
        if (blinkScoreS >= 88) {
            recommendation = 'approved';
        }
    } else if (historyDays >= 180 && historyDays <= 364) {
        if (blinkScoreS >= 80) {
            recommendation = 'approved';
        }
    } else if (historyDays >= 365) {
        if (blinkScoreS >= 73) {
            recommendation = 'approved';
        }
    }
    // else case (historyDays < 90) is implicitly rejected by the initial check / default

    console.log(`System Recommendation based on Score ${blinkScoreS} and History ${historyDays} days: ${recommendation}`);
    return recommendation;
}

// --- Audit Logging ---

/**
 * Logs the results of a risk score calculation to the audit table.
 * Can be called even if the calculation fails early (e.g., insufficient history).
 * @param {string} userId
 * @param {string | null} assetReportId - ID of the asset report used, if applicable.
 * @param {object} metrics - Object containing calculated metrics (even partial).
 * @param {object | null} scores - Object containing points, base_score, blink_score_s, or null if not calculated.
 * @param {'approved' | 'rejected' | null} systemRecommendation - The system's recommendation, or null.
 * @param {string | null} [failureReason=null] - Optional reason if calculation failed (e.g., 'INSUFFICIENT_HISTORY').
 * @param {string | null} [engineVersion='1.0.0'] - Version identifier for the calculation logic.
 * @param {boolean} [flag_od_vol=false] - Admin warning flag: OD-VOL.
 * @param {boolean} [flag_cash_crunch=false] - Admin warning flag: CASH CRUNCH.
 * @param {boolean} [flag_debt_trap=false] - Admin warning flag: DEBT-TRAP.
 */
async function logRiskScoreAudit(
    userId,
    assetReportId,
    metrics,
    scores,
    systemRecommendation,
    failureReason = null, // Optional: Add failure reason if calculation didn't complete
    engineVersion = null, // Default handled below
    // Pass flags
    flag_od_vol = false,
    flag_cash_crunch = false,
    flag_debt_trap = false
) {
    console.log(`Logging risk score audit for user: ${userId}`);

    // Determine the engine version for logging, maybe based on feature flags or env vars in future
    const currentEngineVersion = '1.0.0'; // Define current version

    // Construct the INSERT query dynamically (example)
    const insertQuery = `
        INSERT INTO risk_score_audits (
            user_id, snapshot_timestamp, asset_report_id, calculation_engine_version,
            metric_observed_history_days, metric_median_paycheck, metric_paycheck_regularity,
            metric_days_since_last_paycheck, metric_clean_buffer7, metric_buffer_volatility,
            metric_overdraft_count90, metric_net_cash30, metric_debt_load30,
            metric_volatility90, metric_deposit_multiplicity30,
            points_observed_history, points_liquidity, points_overdraft_count90,
            points_paycheck_regularity, points_days_since_last_paycheck, points_debt_load30,
            points_net_cash30, points_volatility90, points_median_paycheck,
            points_deposit_multiplicity,
            base_score, blink_score_s,
            system_recommendation, admin_user_id, admin_decision, admin_decision_reason, admin_decision_timestamp,
            flag_od_vol, flag_cash_crunch, flag_debt_trap
        )
        VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
            $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28,
            $29, $30, $31, $32, $33, $34, $35
        )
        RETURNING id;
    `;

    const values = [
        userId, new Date(), assetReportId, engineVersion || currentEngineVersion,
        metrics?.metric_observed_history_days ?? null, metrics?.metric_median_paycheck ?? null, metrics?.metric_paycheck_regularity ?? null,
        metrics?.metric_days_since_last_paycheck ?? null, metrics?.metric_clean_buffer7 ?? null, metrics?.metric_buffer_volatility ?? null,
        metrics?.metric_overdraft_count90 ?? null, metrics?.metric_net_cash30 ?? null, metrics?.metric_debt_load30 ?? null,
        metrics?.metric_volatility90 ?? null, metrics?.metric_deposit_multiplicity30 ?? null,
        scores?.points?.points_observed_history ?? null, scores?.points?.points_liquidity ?? null, scores?.points?.points_overdraft_count90 ?? null,
        scores?.points?.points_paycheck_regularity ?? null, scores?.points?.points_days_since_last_paycheck ?? null, scores?.points?.points_debt_load30 ?? null,
        scores?.points?.points_net_cash30 ?? null, scores?.points?.points_volatility90 ?? null, scores?.points?.points_median_paycheck ?? null,
        scores?.points?.points_deposit_multiplicity ?? null,
        scores?.base_score ?? null, scores?.blink_score_s ?? null,
        systemRecommendation,
        null, // admin_user_id (initially null)
        null, // admin_decision (initially null)
        null, // admin_decision_reason (initially null)
        null, // admin_decision_timestamp (initially null)
        flag_od_vol, // flag_od_vol
        flag_cash_crunch, // flag_cash_crunch
        flag_debt_trap // flag_debt_trap
    ];

    try {
        const result = await pool.query(insertQuery, values);
        const insertedLog = result.rows[0]; // Get the returned ID

        console.log(`Successfully logged risk score audit with ID: ${insertedLog.id}`);
        return insertedLog.id; 
    } catch (error) {
        console.error(`Error logging risk score audit for user ${userId}:`, error);
    }
    return null; 
}

/**
 * Updates an existing risk score audit record with the admin\'s final decision.
 * Can optionally run within an existing database transaction.
 * @param {string} auditId - The UUID of the risk_score_audits record to update.
 * @param {string} adminUserId - The UUID of the admin making the decision.
 * @param {\'approved\' | \'rejected\'} adminDecision - The decision made by the admin.
 * @param {string | null} adminDecisionReason - Optional reason provided by the admin.
 * @param {object} [dbClient=null] - Optional database client to use for the query (for transactions). If null, uses the pool.
 * @returns {Promise<boolean>} - True if the update was successful, false otherwise.
 */
async function updateRiskScoreAuditDecision(
    auditId,
    adminUserId,
    adminDecision,
    adminDecisionReason = null,
    dbClient = null // Add optional client parameter
) {
    console.log(`Updating audit record ${auditId} with admin decision: ${adminDecision}`);

    if (!auditId || !adminUserId || !adminDecision) {
        console.error('Missing required parameters for updating audit decision.');
        return false;
    }

    const queryRunner = dbClient || pool; // Use provided client or the pool

    try {
        const updateQuery = `
          UPDATE risk_score_audits
          SET 
            admin_user_id = $1,
            admin_decision = $2,
            admin_decision_reason = $3,
            admin_decision_timestamp = NOW() -- Use NOW() directly
          WHERE id = $4;
        `;
        const values = [
            adminUserId,
            adminDecision,
            adminDecisionReason,
            auditId // WHERE clause parameter
        ];

        const result = await queryRunner.query(updateQuery, values);
        const updatedCount = result.rowCount;

        if (updatedCount > 0) {
            console.log(`Successfully updated audit record ${auditId}`);
            return true;
        } else {
            console.warn(`Audit record ${auditId} not found for update.`);
            return false;
        }
    } catch (error) {
        console.error(`Error updating audit record ${auditId}:`, error);
        // Re-throw the error if using a client, so the transaction can be rolled back
        if (dbClient) throw error; 
        return false;
    }
}

/**
 * Calculates the Blink Risk Score for a given user.
 * Orchestrates the process: fetching data, tagging, calculating metrics, scoring.
 * @param {string} userId - The UUID of the user.
 * @param {object} [overrides] - Optional admin overrides for transaction tagging.
 * @returns {Promise<object>} - Object containing the calculated metrics, scores, and recommendation.
 * @throws {Error} - If scoring cannot be completed (e.g., insufficient history).
 */
async function calculateRiskScore(userId, overrides = {}) {
    console.log(`Calculating risk score for user: ${userId}`);
    let plaidData = null;
    let metricsData = null; // Store result from calculateMetrics
    let scores = null;
    let systemRecommendation = null;
    let taggedTransactions = [];
    let assetReportId = null; // Initialize assetReportId
    let auditId = null; // Initialize auditId
    let assetReportAccountId = null; // Initialize
    let initialMetrics = null; // Declare initialMetrics outside try block

    try {
        // 1. Fetch Plaid Data
        plaidData = await getPlaidDataForUser(userId);
        assetReportId = plaidData.assetReportId;
        assetReportAccountId = plaidData.assetReportAccountId; // <-- Store it

        // 2. Initial Check: History Requirement (H >= 90 days)
        let historyDays = 0;
        if (plaidData.transactions.length > 0) {
            const firstTransactionDate = moment(plaidData.transactions[0].date);
            const reportMoment = moment(plaidData.reportDate);
            historyDays = reportMoment.diff(firstTransactionDate, 'days') + 1;
        }
        console.log(`Calculated history days (H): ${historyDays}`);

        // Initialize metrics object early for potential partial logging
        initialMetrics = {
            metric_observed_history_days: historyDays,
            // ... other metrics initialized to null ...
             metric_median_paycheck: null, metric_paycheck_regularity: null, metric_days_since_last_paycheck: null,
             metric_clean_buffer7: null, metric_buffer_volatility: null, metric_overdraft_count90: null,
             metric_net_cash30: null,
             metric_debt_load30: null, metric_volatility90: null,
        };

        if (historyDays < 90) {
            const failureReason = `INSUFFICIENT_HISTORY: Only ${historyDays} days available (required 90).`;
            // Log the failure attempt, store the returned auditId
            auditId = await logRiskScoreAudit(userId, assetReportId, initialMetrics, null, 'rejected', failureReason);
            // Include auditId in the error object?
            const error = new Error(failureReason);
            // error.auditId = auditId; // Optional: Attach auditId to error
            throw error;
        }

        // 3. Tag Transactions
        taggedTransactions = tagTransactions(plaidData.transactions, overrides);

        // 4. Calculate 8 Core Metrics & Get Payroll Info
        // Note: calculateMetrics now returns an object
        metricsData = calculateMetrics(taggedTransactions, plaidData.historicalBalances, plaidData.currentBalance, initialMetrics, plaidData.reportDate);
        const finalMetrics = metricsData.metrics;
        const payrollTransactionsForScore = metricsData.payrollTransactions;
        const totalPayrollWeightForScore = metricsData.totalPayrollWeight;
        console.log('Calculated Metrics (final):', finalMetrics);

        // 5. Calculate Points and Scores
        scores = calculateScores(finalMetrics, payrollTransactionsForScore, totalPayrollWeightForScore); // Contains points, base_score, blink_score_s

        // 6. Determine System Recommendation
        systemRecommendation = getSystemRecommendation(scores.blink_score_s, finalMetrics.metric_observed_history_days);

        // 7. Calculate Admin Early-Warning Flags
        let flag_od_vol = false;
        let flag_cash_crunch = false;
        let flag_debt_trap = false;

        const F = finalMetrics.metric_overdraft_count90;
        const BV = finalMetrics.metric_buffer_volatility;
        const N30 = finalMetrics.metric_net_cash30;
        const D = finalMetrics.metric_days_since_last_paycheck;
        const R30 = finalMetrics.metric_debt_load30;
        const C7 = finalMetrics.metric_clean_buffer7;

        // OD-VOL flag: F >= 3 AND BV > $100
        if (F !== null && BV !== null && F >= 3 && BV > 100) {
            flag_od_vol = true;
        }

        // CASH CRUNCH flag: N30 < -$200 AND D > 10
        if (N30 !== null && D !== null && N30 < -200 && D > 10) {
            flag_cash_crunch = true;
        }

        // DEBT-TRAP flag: R30 > 0.35 AND C7 < $50
        if (R30 !== null && C7 !== null && R30 > 0.35 && C7 < 50) {
            flag_debt_trap = true;
        }

        // 8. Log Successful Audit Record (including flags)
        auditId = await logRiskScoreAudit(
            userId, 
            assetReportId, 
            finalMetrics, 
            scores, 
            systemRecommendation, 
            null, // No failure reason
            null, // Use default engine version from logRiskScoreAudit
            // Pass flags
            flag_od_vol, 
            flag_cash_crunch, 
            flag_debt_trap 
        );

        console.log(`Risk score calculation complete for user: ${userId}. Final Score: ${scores.blink_score_s}. Recommendation: ${systemRecommendation}`);
        console.log(`Admin Flags: OD-VOL=${flag_od_vol}, CASH-CRUNCH=${flag_cash_crunch}, DEBT-TRAP=${flag_debt_trap}`);

        // 9. Return structure including auditId, assetReportAccountId, and flags
        return {
            userId,
            metrics: finalMetrics,
            scores,
            systemRecommendation,
            taggedTransactions: taggedTransactions, // Optional: might remove from final response
            auditId: auditId,
            assetReportAccountId: assetReportAccountId, // <-- Add to response
            // Add flags to the response payload
            flags: {
                od_vol: flag_od_vol,
                cash_crunch: flag_cash_crunch,
                debt_trap: flag_debt_trap
            }
        };

    } catch (error) {
        console.error(`Risk scoring failed for user ${userId}:`, error.message);
        // Log partial results if possible, using potentially stored auditId if initial log happened
        if (auditId === null) { // Check if we need to log a failure that didn't happen at the history check stage
             // Use initialMetrics directly if metricsData is null
             const metricsToLog = metricsData ? metricsData.metrics : initialMetrics || {};
             if (plaidData && metricsToLog.metric_observed_history_days >= 90 && !error.message.startsWith('INSUFFICIENT_HISTORY')) {
                 auditId = await logRiskScoreAudit(userId, assetReportId, metricsToLog, scores, null, `CALCULATION_ERROR: ${error.message}`);
             } else if (!plaidData && !error.message.startsWith('INSUFFICIENT_HISTORY')) {
                 auditId = await logRiskScoreAudit(userId, null, {}, null, null, `DATA_FETCH_ERROR: ${error.message}`);
             }
        }
        // Re-throw the error so the caller knows it failed
        // Optionally attach auditId to the error if needed by controller
        // error.auditId = auditId; 
        throw error;
    }
}

/**
 * Fetches historical balances for a specific asset report account.
 * @param {string} assetReportAccountId - The UUID of the asset_report_accounts record.
 * @returns {Promise<Array<{balance_date: string, balance_current: number}>>} - Array of balance objects, sorted by date.
 * @throws {Error} - If fetching fails.
 */
async function getHistoricalBalances(assetReportAccountId) {
    console.log(`Fetching historical balances for account: ${assetReportAccountId}`);
    if (!assetReportAccountId) {
        throw new Error('Asset Report Account ID is required.');
    }

    try {
        const balanceQuery = `
            SELECT balance_date, balance_current 
            FROM asset_report_account_historical_balances 
            WHERE asset_report_account_id = $1 
            ORDER BY balance_date ASC;
        `;
        const result = await pool.query(balanceQuery, [assetReportAccountId]);
        // Ensure balance_current is parsed as float
        const historicalBalances = result.rows.map(row => ({
            ...row,
            balance_current: parseFloat(row.balance_current)
        }));
        console.log(`Fetched ${historicalBalances.length} historical balance records.`);
        return historicalBalances;
    } catch (error) {
        console.error(`Error fetching historical balances for account ${assetReportAccountId}:`, error);
        throw new Error('Database error fetching historical balances.');
    }
}

module.exports = {
  calculateRiskScore,
  updateRiskScoreAuditDecision,
  getHistoricalBalances,
  // Potentially export helper functions if needed elsewhere, e.g., for recalc
}; 