# Assisted drafting token budget

Four distinct header-only calls serve twelve complete table rows. Before running: 856–1,716 estimated input tokens plus at most 1,024 output tokens. Actual: **1,376 input + 654 output = 2,030 tokens**. Each call used 492, 514, 512 and 512 total tokens. This is comfortably below the supplied 200k/day allowance, but it does not automatically interpret all 46 clauses: twenty-four numeric clauses still need composition/context and ten are nonnumeric.

The previous production request used 3,231 input + 1,295 output on its first clause. Its full 92-request plan estimated 156,649–313,373 input plus a 153,088 output cap. Contracts and covered capabilities differ, so this is not a controlled efficiency or accuracy comparison.

Alternative checked before adding anything: Cloudflare publishes 10,000 free neurons/day and a default 300 text requests/minute for non-paid models. Neurons cannot be equated to tokens without a model. No account-specific limits, models or schema support were verified; CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are absent. No Cloudflare calls or provider integration were added. Cerebras currently describes a payment-method-backed, expiring trial, not a permanently free allowance; it was not enabled.

Sources and per-call usage: [budget record](../reports/assisted-token-budget.json). Only regulation header text and relevant type vocabulary went to Groq. No drawings, plan values, gold labels or keys were logged or uploaded.
