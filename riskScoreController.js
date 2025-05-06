const riskScoringService = require('../services/riskScoringService');
const { pool } = require('../../config/db'); // Import the pool
const { Resend } = require('resend'); // Import Resend
const config = require('../../config'); // Import config to get API keys/emails

// Instantiate Resend client outside the handler for efficiency
const resend = new Resend(config.resendApiKey);

/**
 * Controller to handle risk score calculation requests.
 * POST /api/risk-score/calculate/:userId
 * Body (optional): { overrides: { transactionId1: { is_payroll: false }, ... } }
 */
async function calculateUserRiskScore(req, res) {
    const { userId } = req.params;
    const overrides = req.body.overrides || {}; // Get overrides from request body, default to empty object

    if (!userId) {
        return res.status(400).json({ message: 'User ID parameter is required.' });
    }

    try {
        console.log(`API: Received request to calculate risk score for user ${userId}`);
        const result = await riskScoringService.calculateRiskScore(userId, overrides);

        // Send back the detailed result including metrics, scores, recommendation, and tagged transactions
        console.log(`API: Successfully calculated risk score for user ${userId}.`);
        return res.status(200).json(result);

    } catch (error) {
        console.error(`API Error calculating risk score for user ${userId}:`, error);

        // Handle specific known errors
        if (error.message.startsWith('INSUFFICIENT_HISTORY')) {
            return res.status(400).json({ message: error.message });
        }
        if (error.message.includes('No asset report found') || error.message.includes('No associated account found')) {
             return res.status(404).json({ message: 'Required Plaid data not found for the user.' });
        }

        // Generic internal server error for other unexpected issues
        return res.status(500).json({ message: 'Internal server error during risk score calculation.' });
    }
}

/**
 * Controller to handle recording the admin's final decision on a risk score audit.
 * PATCH /api/risk-score/audit/:auditId/decision
 * Body: { adminDecision: ('approved'|'rejected'), adminDecisionReason?: string }
 */
async function recordAdminDecision(req, res) {
    const { auditId } = req.params;
    const { adminDecision, adminDecisionReason } = req.body;
    const adminUserId = req.admin?.id; // Get admin ID from middleware
    let userId = null; // Declare userId here to make it available later

    // Initial validation
    if (!auditId) {
        return res.status(400).json({ message: 'Audit ID parameter is required.' });
    }
    if (!adminDecision || !['approved', 'rejected'].includes(adminDecision)) {
        return res.status(400).json({ message: "Valid adminDecision ('approved' or 'rejected') is required in the request body." });
    }
    if (!adminUserId) {
        return res.status(401).json({ message: 'Admin authentication required.' });
    }

    let client; // Define client outside try for the finally block
    try {
        console.log(`API: Received request to record admin decision for audit ${auditId}`);

        // Map frontend decision to expected DB enum value
        let dbAdminDecision;
        if (adminDecision === 'approved') {
            dbAdminDecision = 'approved'; // Lowercase matches enum value
        } else if (adminDecision === 'rejected') {
            dbAdminDecision = 'denied';   // Map 'rejected' from frontend to 'denied' for DB
        } else {
            // This case should ideally not be reached due to prior validation
            console.error(`Invalid adminDecision received in controller: ${adminDecision}`);
            return res.status(400).json({ message: "Invalid admin decision value provided." });
        }

        // Start transaction
        client = await pool.connect();
        await client.query('BEGIN');

        // 1. Update the risk_score_audits table using the transaction client and the mapped value
        const updateSuccess = await riskScoringService.updateRiskScoreAuditDecision(
            auditId,
            adminUserId,
            dbAdminDecision, // Use mapped value
            adminDecisionReason,
            client // Pass the client to the service function
        );

        if (!updateSuccess) {
            // If update failed (e.g., auditId not found), rollback and respond
            await client.query('ROLLBACK');
            client.release();
            console.warn(`API: Failed to update audit record ${auditId} (possibly not found).`);
            return res.status(404).json({ message: 'Failed to record admin decision. Audit record not found.' });
        }

        // 2. Get the user_id associated with this audit record
        const userQuery = 'SELECT user_id FROM risk_score_audits WHERE id = $1';
        const userResult = await client.query(userQuery, [auditId]);

        if (userResult.rows.length === 0) {
             // Should not happen if updateSuccess was true, but safety check
            await client.query('ROLLBACK');
            client.release();
            console.error(`API: Inconsistency - Audit record ${auditId} updated but user_id not found.`);
            return res.status(500).json({ message: 'Internal server error: Audit record inconsistency.' });
        }
        // Assign to the outer scope userId variable
        userId = userResult.rows[0].user_id;

        // 3. Insert into user_cash_advance_approvals using the mapped value
        // const approvalStatusEnum = adminDecision; // Old direct mapping
        const approvalStatusEnum = dbAdminDecision; // Use mapped value
        const insertApprovalQuery = `
            INSERT INTO user_cash_advance_approvals (user_id, status, performed_by, reason, created_at)
            VALUES ($1, $2, $3, $4, NOW());
        `;
        await client.query(insertApprovalQuery, [
            userId,
            approvalStatusEnum, // Use mapped value
            adminUserId,
            adminDecisionReason
        ]);

        // 4. Commit the transaction
        await client.query('COMMIT');
        console.log(`API: Successfully committed database changes for audit ${auditId}.`);
        
    } catch (error) {
        console.error(`API Error during database transaction for audit ${auditId}:`, error);
        if (client) {
            try { await client.query('ROLLBACK'); } catch (rbErr) { console.error('Rollback Error:', rbErr); }
        }
        return res.status(500).json({ message: 'Internal server error while recording admin decision.' });
    } finally {
         if (client) {
            client.release(); // Ensure client is always released after transaction attempt
         }
    }

    // --- Send Notification Email Directly (Outside Transaction) ---
    if (userId) { // Only proceed if userId was successfully fetched during transaction
        try {
            // Fetch user email and first name
            const userDetailsQuery = 'SELECT email, first_name FROM users WHERE id = $1';
            const userDetailsResult = await pool.query(userDetailsQuery, [userId]); // Use pool directly

            if (userDetailsResult.rows.length > 0) {
                const user = userDetailsResult.rows[0];
                const templateCode = adminDecision === 'approved' ? 'ADMIN_ADVANCE_APPROVED' : 'ADMIN_ADVANCE_REJECTED';
                const context = { firstName: user.first_name }; // Basic context

                // Fetch the email template from the database
                const templateQuery = 'SELECT title_template, message_template FROM notification_templates WHERE code = $1 AND is_active = true';
                const templateResult = await pool.query(templateQuery, [templateCode]);

                if (templateResult.rows.length > 0) {
                    const template = templateResult.rows[0];

                    // Simple template rendering (replace placeholders like {{firstName}})
                    const subject = template.title_template.replace(/{{firstName}}/g, context.firstName);
                    let htmlBody = template.message_template.replace(/{{firstName}}/g, context.firstName);

                    console.log(`API: Attempting to send email '${templateCode}' to user ${userId} (${user.email})`);

                    // Send email using Resend
                    const { data, error } = await resend.emails.send({
                        from: config.emailFrom, // Use configured sender email
                        to: [user.email], // User's email address
                        subject: subject,
                        html: htmlBody,
                    });

                    if (error) {
                        // Log Resend specific error but don't fail the request
                        console.error(`API: Resend error sending email for user ${userId}, template ${templateCode}:`, error);
                    } else {
                        console.log(`API: Successfully sent email '${templateCode}' to user ${userId}. Resend ID: ${data?.id}`);
                    }

                } else {
                    console.warn(`API: Could not find active template with code '${templateCode}' to send email.`);
                }
            } else {
                console.warn(`API: Could not find user ${userId} details to send email notification.`);
            }
        } catch (emailError) {
            // Log any other error during email preparation/sending
            console.error(`API: Generic error sending notification email for user ${userId} after audit ${auditId} decision:`, emailError);
            // Log this error, but don't send a 500 response as the main action succeeded.
        }
    } else {
        console.warn(`API: Skipping email notification for audit ${auditId} because userId could not be determined.`);
    }

    // --- Send Success Response --- 
    // Send successful response for the main action (admin decision recording)
    console.log(`API: Completed request to record admin decision for audit ${auditId}.`);
    return res.status(200).json({ message: 'Admin decision recorded successfully.' });
}

/**
 * Controller to get historical balances for a specific account.
 * GET /api/accounts/:accountId/historical-balances
 */
async function getAccountHistoricalBalances(req, res) {
    const { accountId } = req.params; // This is the asset_report_account_id UUID

    if (!accountId) {
        return res.status(400).json({ message: 'Account ID parameter is required.' });
    }

    try {
        console.log(`API: Received request for historical balances for account ${accountId}`);
        const balances = await riskScoringService.getHistoricalBalances(accountId);
        
        // Check if balances were found (service might throw, but belt-and-suspenders)
        if (!balances) {
             // This case might not be reached if service throws, but good practice
             return res.status(404).json({ message: 'Historical balances not found for this account.' });
        }

        console.log(`API: Successfully fetched ${balances.length} historical balances for account ${accountId}.`);
        return res.status(200).json(balances); // Return the array of balance data

    } catch (error) {
        console.error(`API Error fetching historical balances for account ${accountId}:`, error);
        // Handle specific errors if needed, e.g., invalid UUID format
        if (error.message.includes('Database error')) {
            return res.status(500).json({ message: 'Database error fetching historical balances.' });
        } 
        // Default internal server error
        return res.status(500).json({ message: 'Internal server error fetching historical balances.' });
    }
}

module.exports = {
    calculateUserRiskScore,
    recordAdminDecision,
    getAccountHistoricalBalances,
}; 