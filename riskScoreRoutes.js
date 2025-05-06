const express = require('express');
const riskScoreController = require('../controllers/riskScoreController');
// TODO: Add authentication middleware if needed
const { verifyAdminToken } = require('../middleware/authMiddleware'); // Import the actual middleware
const { pool } = require('../../config/db'); // Import pool for direct DB access
const { Resend } = require('resend'); // Import Resend
const config = require('../../config'); // Import config

// Instantiate Resend client
const resend = new Resend(config.resendApiKey);

const router = express.Router();

/**
 * @swagger
 * /risk-score/calculate/{userId}:
 *   post:
 *     summary: Calculate Blink Risk Score for a user
 *     tags: [RiskScore]
 *     parameters:
 *       - in: path
 *         name: userId
 *         required: true
 *         schema:
 *           type: string
 *           format: uuid
 *         description: The UUID of the user to calculate the score for.
 *     requestBody:
 *       required: false
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             properties:
 *               overrides:
 *                 type: object
 *                 description: Optional overrides for transaction tags (e.g., marking a specific transaction as not payroll).
 *                 additionalProperties:
 *                   type: object
 *                   properties:
 *                     is_payroll:
 *                       type: boolean
 *                     is_loanpay:
 *                       type: boolean
 *           example:
 *             overrides: {
 *               "plaid_txn_id_123": { "is_payroll": false },
 *               "plaid_txn_id_456": { "is_loanpay": false }
 *             }
 *     responses:
 *       200:
 *         description: Successfully calculated risk score.
 *         content:
 *           application/json:
 *             schema:
 *              $ref: '#/components/schemas/RiskScoreResult' # Define this schema elsewhere
 *       400:
 *         description: Bad Request (e.g., Missing userId, Insufficient History).
 *       404:
 *         description: Not Found (e.g., User or Plaid data not found).
 *       500:
 *         description: Internal Server Error.
 *     security:
 *       - bearerAuth: [] # Assuming admin authentication is needed
 */
// Apply authentication middleware if this endpoint needs protection
router.post('/calculate/:userId', verifyAdminToken, riskScoreController.calculateUserRiskScore); // Apply middleware
// router.post('/calculate/:userId', riskScoreController.calculateUserRiskScore); // Currently unprotected for testing

/**
 * @swagger
 * /risk-score/audit/{auditId}/decision:
 *   patch:
 *     summary: Record admin decision on a risk score audit
 *     tags: [RiskScore]
 *     parameters:
 *       - in: path
 *         name: auditId
 *         required: true
 *         schema:
 *           type: string
 *           format: uuid
 *         description: The UUID of the risk_score_audits record.
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             properties:
 *               adminDecision:
 *                 type: string
 *                 enum: [approved, rejected]
 *                 description: The final decision made by the admin.
 *               adminDecisionReason:
 *                 type: string
 *                 description: Optional free-text reason for the decision (especially for overrides).
 *             required:
 *               - adminDecision
 *           example:
 *             adminDecision: "rejected"
 *             adminDecisionReason: "Manual review showed inconsistent income patterns not caught by heuristics."
 *     responses:
 *       200:
 *         description: Admin decision recorded successfully.
 *       400:
 *         description: Bad Request (e.g., Missing auditId or invalid adminDecision).
 *       401:
 *         description: Unauthorized (Admin authentication failed).
 *       404:
 *         description: Not Found (Audit record not found).
 *       500:
 *         description: Internal Server Error.
 *     security:
 *       - bearerAuth: [] # Assuming admin authentication is needed
 */
// Apply authentication middleware if this endpoint needs protection
router.patch('/audit/:auditId/decision', verifyAdminToken, riskScoreController.recordAdminDecision); // Apply middleware
// router.patch('/audit/:auditId/decision', riskScoreController.recordAdminDecision); // Currently unprotected

// --- DEVELOPMENT ONLY: Test Email Endpoint (Approved) ---
// WARNING: Remove this route before deploying to production!
router.get('/test-email/approved', async (req, res) => {
    console.log("DEV ONLY: Hit test-email/approved endpoint");
    const templateCode = 'ADMIN_ADVANCE_APPROVED';
    const recipientEmail = req.query.recipient; // Get recipient from query param
    const testContext = { firstName: 'Alejandro [Test]' }; 

    // Validate recipient
    if (!recipientEmail) {
        console.error("DEV ONLY: Missing 'recipient' query parameter.");
        return res.status(400).json({ message: "Missing 'recipient' query parameter. Add ?recipient=email@example.com to the URL." });
    }

    try {
        // Fetch the email template from the database
        const templateQuery = 'SELECT title_template, message_template FROM notification_templates WHERE code = $1 AND is_active = true';
        const templateResult = await pool.query(templateQuery, [templateCode]);

        if (templateResult.rows.length === 0) {
            console.error(`DEV ONLY: Template '${templateCode}' not found or inactive.`);
            return res.status(404).json({ message: `Template '${templateCode}' not found or inactive.` });
        }
        const template = templateResult.rows[0];

        // Render template
        const subject = template.title_template.replace(/{{firstName}}/g, testContext.firstName);
        const htmlBody = template.message_template.replace(/{{firstName}}/g, testContext.firstName);

        console.log(`DEV ONLY: Attempting to send test email '${templateCode}' to ${recipientEmail}`);

        // Send email using Resend
        const { data, error } = await resend.emails.send({
            from: config.emailFrom,
            to: [recipientEmail], // Use recipient from query param
            subject: `[TEST] ${subject}`, 
            html: htmlBody,
        });

        if (error) {
            console.error(`DEV ONLY: Resend error sending test email:`, error);
            return res.status(500).json({ message: 'Resend error', error: error });
        } else {
            console.log(`DEV ONLY: Successfully sent test email. Resend ID: ${data?.id}`);
            return res.status(200).json({ message: 'Test email sent successfully.', resendId: data?.id });
        }

    } catch (err) {
        console.error(`DEV ONLY: Error in test email endpoint:`, err);
        return res.status(500).json({ message: 'Internal server error during test email.', error: err.message });
    }
});

// --- DEVELOPMENT ONLY: Test Email Endpoint (Rejected) ---
// WARNING: Remove this route before deploying to production!
router.get('/test-email/rejected', async (req, res) => {
    console.log("DEV ONLY: Hit test-email/rejected endpoint");
    const templateCode = 'ADMIN_ADVANCE_REJECTED'; 
    const recipientEmail = req.query.recipient; // Get recipient from query param
    const testContext = { firstName: 'Alejandro [Test]' };

    // Validate recipient
    if (!recipientEmail) {
        console.error("DEV ONLY: Missing 'recipient' query parameter.");
        return res.status(400).json({ message: "Missing 'recipient' query parameter. Add ?recipient=email@example.com to the URL." });
    }

    try {
        // Fetch the email template from the database
        const templateQuery = 'SELECT title_template, message_template FROM notification_templates WHERE code = $1 AND is_active = true';
        const templateResult = await pool.query(templateQuery, [templateCode]);

        if (templateResult.rows.length === 0) {
            console.error(`DEV ONLY: Template '${templateCode}' not found or inactive.`);
            return res.status(404).json({ message: `Template '${templateCode}' not found or inactive.` });
        }
        const template = templateResult.rows[0];

        // Render template
        const subject = template.title_template.replace(/{{firstName}}/g, testContext.firstName);
        const htmlBody = template.message_template.replace(/{{firstName}}/g, testContext.firstName);

        console.log(`DEV ONLY: Attempting to send test email '${templateCode}' to ${recipientEmail}`);

        // Send email using Resend
        const { data, error } = await resend.emails.send({
            from: config.emailFrom,
            to: [recipientEmail], // Use recipient from query param
            subject: `[TEST] ${subject}`, 
            html: htmlBody,
        });

        if (error) {
            console.error(`DEV ONLY: Resend error sending test email:`, error);
            return res.status(500).json({ message: 'Resend error', error: error });
        } else {
            console.log(`DEV ONLY: Successfully sent test email. Resend ID: ${data?.id}`);
            return res.status(200).json({ message: 'Test email sent successfully.', resendId: data?.id });
        }

    } catch (err) {
        console.error(`DEV ONLY: Error in test email endpoint:`, err);
        return res.status(500).json({ message: 'Internal server error during test email.', error: err.message });
    }
});

module.exports = router; 