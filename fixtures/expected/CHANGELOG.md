# Expected-fixture label corrections

- 2026-09-30, company_a.json / company_a.ratios.json, tech lead's instruction: `total_debt` FY2024 (was 32,053) and FY2023 (was 29,622) changed to null, `lease_not_separately_presented` warning replaced by `missing_item`; `debt_to_equity` (was 1.421103968078 / 1.426603737238) changed to null, reason `missing_input`. Reason: the face line 'Financial liabilities' includes derivatives and other financial liabilities (note 15C), so it is not interest-bearing borrowings + leases (CLAUDE.md). Decided 2026-09-29. Other items unchanged.
