## 2026-03-20 Submission Summary

Cloud Run log review for `tripletex-agent`.

### Confirmed failures

1. `create_invoice` with order -> invoice -> payment flow sends `markAsPaid` to `POST /invoice`.
   - Evidence:
     - `2026-03-20 18:31:33`
     - `Tripletex API error 422 on POST /invoice`
     - validation message: `field":"markAsPaid","message":"Feltet eksisterer ikke i objektet."`
   - Impact:
     - Tier 2 invoice/payment prompts fail with `502`.

2. `create_dimension_voucher` uses `POST /dimension`, which the proxy rejects with `404`.
   - Evidence:
     - `2026-03-20 18:34:59`
     - `Tripletex API error 404 on POST /dimension`
     - error category already classified as `wrong_endpoint`
   - Impact:
     - dimension-voucher prompts fail immediately.

3. Older revision failures before the latest deploy included parser/validation blockers for:
   - payment reversal prompt missing customer extraction
   - German multiline order/invoice/payment prompt missing order line extraction
   - These appear before the later successful redeploy and should not be treated as current regressions unless reproduced again.

4. Environment blocker still exists for some invoice prompts.
   - Evidence:
     - `2026-03-20 18:33:12`
     - `Faktura kan ikke opprettes før selskapet har registrert et bankkontonummer.`
   - Impact:
     - this is not a parser bug; it is a Tripletex company configuration blocker.

### Confirmed successes after redeploy

1. Payment reversal prompt later succeeded.
   - Evidence:
     - `2026-03-20 18:32:20` start
     - `GET /v2/customer`
     - `POST /v2/order`
     - `POST /v2/invoice`
     - `solve_completed`

2. Customer creation succeeded.
   - Evidence:
     - `2026-03-20 18:33:33`
     - `POST /v2/customer`
     - `solve_completed`

3. Project creation succeeded in German and French.

### Immediate code follow-up

1. Remove `markAsPaid`, `paymentDate`, and `amountPaidCurrency` from invoice payloads sent to `/invoice`.
2. Handle payment registration through the correct Tripletex endpoint or supported fallback instead of overloading `/invoice`.
3. Verify the correct endpoint path for dimensions in the proxy and update `create_dimension_voucher` accordingly.
4. Add regression tests that fail on:
   - `markAsPaid` present in `/invoice` payload
   - `POST /dimension` returning `404`

