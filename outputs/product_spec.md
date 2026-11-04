# Product specification (draft): Solar Yield Parametric Cover

- **Insured:** 3 kVA grid-connected rooftop solar system, pincode 380006 (Ahmedabad)
- **Index:** annual (1 Jan - 31 Dec) total of ERA5-Land surface solar radiation downwards, in kWh/m2, averaged over the surrounding grid cells
- **Trigger:** 1923.6 kWh/m2 (99% of the 2005-2024 mean of 1943.0 kWh/m2)
- **Exit:** 1893.7 kWh/m2 (5th percentile of 2005-2024 annual values)
- **Payout:** linear between trigger and exit: Rs 88.5 per kWh/m2 below the trigger
- **Maximum payout:** Rs 2645.00 (10% of annual savings at P50 = Rs 26450.00)
- **Formula:** payout = min(Rs 2645.00, max(0, 88.5 x (1923.6 - index)))
- **Settlement:** once the full year of ERA5-Land data is available; no claim filing, no loss adjustment
