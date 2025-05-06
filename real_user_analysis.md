# Real User Risk Score Analysis

I've retrieved data for 5 real users from the MCP Blink database and scored them using our new LightGBM risk model. Here's a comparison of their original scores and our new model's predictions:

## Score Comparison Table

| User ID | Original Score | New ML Score | Key Risk Factors |
|---------|---------------|--------------|------------------|
| 0004e939-3dd6-485f-8f9a-2e14ce8dc62a | 41 | 50 | No paycheck data, high volatility (3.75), no buffer |
| 00327fb9-e55e-4482-a572-650c0ac70a7e | 32 | 70 | Negative cash flow (-130), low buffer, good paycheck regularity |
| 003826a8-d4a8-4296-86a4-4b82aae62bf4 | 47 | 50 | No paycheck data, negative cash flow, very high clean buffer |
| 0078cc56-562a-45de-b84f-c5c47488845f | 44 | 50 | Low paycheck ($64), no regularity, positive cash flow |
| 007b3552-7e1a-4752-aa91-8c586cfc5708 | 41 | 60 | High paycheck ($1,424), recent paycheck, negative buffer, overdraft |

## Key Observations

1. **User 00327fb9**: Biggest score improvement (32 → 70)
   - Despite negative cash flow, this user has excellent paycheck regularity (5.52)
   - Long observed history (548 days) shows stability
   - Low debt load ratio (0.0034) indicates minimal debt burden

2. **User 007b3552**: Moderate score improvement (41 → 60)
   - Highest paycheck amount in the group ($1,424)
   - Very recent paycheck (3 days ago) indicates current income
   - Negative buffer (-179) and overdraft are concerning but outweighed by income

3. **User 003826a8**: Nearly unchanged score (47 → 50)
   - Unusual profile with very high clean buffer (658.94) but no paycheck data
   - Highest deposit multiplicity (15 sources of income)
   - Model balances these unusual factors

4. **User 0004e939**: Slight improvement (41 → 50)
   - Limited positive signals
   - Long history (231 days) is the main positive factor
   - No paycheck, no buffer, but also no overdrafts

5. **User 0078cc56**: Slight improvement (44 → 50)
   - Small paycheck amount ($64)
   - Long history (392 days)
   - Positive cash flow (small but positive at $3.42)

## Model Assessment

The new model appears to:
1. Put higher emphasis on paycheck regularity and recency
2. Value long observed history as a stability signal
3. Be more lenient with negative cash flow when other positive indicators exist
4. Give more weight to income level in the overall assessment

For these 5 real users, the model:
- Increased scores for all users
- Provided greater differentiation (scores ranging from 50-70 rather than 32-47)
- Aligned with the expected risk factors from our analysis 