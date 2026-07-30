"""Test nbsc library for NBS macro data."""
import nbsc

print("Testing nbsc...")
cpi = nbsc.get_annual_inflation("2025")
print(f"CPI 2025: {len(cpi)} rows")
pmi = nbsc.get_manufacturing_pmi("2025")
print(f"PMI 2025: {len(pmi)} rows")
m2 = nbsc.get_m2_yoy("2025")
print(f"M2 YoY 2025: {len(m2)} rows")
gdp = nbsc.get_gdp_nominal("2025")
print(f"GDP 2025: {len(gdp)} rows")
print("nbsc OK")
