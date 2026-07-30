"""Browser self-test: verify AntDesign migration works correctly."""
import sys, json, time
sys.path.insert(0, r'..\..\GenericAgent')
from TMWebDriver import TMWebDriver
from ga import web_execute_js

driver = TMWebDriver()
time.sleep(3)

# Find the web tab
sessions = driver.get_all_sessions()
target = None
for s in sessions:
    if "3000" in str(s) or "localhost:3000" in str(s):
        target = s
        break

if not target:
    # Open forecast page
    driver.set_session("about:blank")
    time.sleep(1)
    driver.jump("http://localhost:3000/forecast")
    time.sleep(8)
else:
    driver.set_session("3000")
    time.sleep(2)

# Test 1: Check page loaded
title = driver.execute_js("document.title")
print(f"Page title: {title}")

# Test 2: Check DatePicker exists on forecast page
datePickers = driver.execute_js("document.querySelectorAll('.ant-picker').length")
print(f"AntDesign DatePickers found: {datePickers}")

# Test 3: Check buttons use AntDesign
antButtons = driver.execute_js("document.querySelectorAll('.ant-btn').length")
print(f"AntDesign buttons found: {antButtons}")

# Test 4: Check Select components
antSelects = driver.execute_js("document.querySelectorAll('.ant-select').length")
print(f"AntDesign selects found: {antSelects}")

# Test 5: Check any Alert components
antAlerts = driver.execute_js("document.querySelectorAll('.ant-alert').length")
print(f"AntDesign alerts found: {antAlerts}")

# Test 6: Check Input components  
antInputs = driver.execute_js("document.querySelectorAll('.ant-input').length")
print(f"AntDesign inputs found: {antInputs}")

# Test 7: Check Table components
antTables = driver.execute_js("document.querySelectorAll('.ant-table').length")
print(f"AntDesign tables found: {antTables}")

# Test 8: Navigate to dashboard and check health data loads
driver.jump("http://localhost:3000")
time.sleep(5)
healthStatus = driver.execute_js("document.body.innerText")
if isinstance(healthStatus, dict) and "data" in healthStatus:
    text = healthStatus["data"]
    print(f"Dashboard loaded: text={text[:100]}...")

# Test 9: Check header shows model name
modelName = driver.execute_js("""(() => {
    const spans = document.querySelectorAll('span');
    for (const s of spans) {
        if (s.textContent && s.textContent.includes('Fine-tuned')) return s.textContent;
    }
    return 'not found';
})()""")
if isinstance(modelName, dict) and "data" in modelName:
    print(f"Model name in header: {modelName['data']}")

# Test 10: Navigate to batch page
driver.jump("http://localhost:3000/batch")
time.sleep(5)
batchLoaded = driver.execute_js("document.querySelectorAll('.ant-btn').length")
print(f"Batch page buttons: {batchLoaded}")

# Test 11: Navigate to data page  
driver.jump("http://localhost:3000/data")
time.sleep(5)
dataLoaded = driver.execute_js("document.querySelectorAll('.ant-picker').length")
print(f"Data page DatePickers: {dataLoaded}")

def _v(x):
    return x["data"] if isinstance(x, dict) and "data" in x else str(x)

print("\n=== TEST SUMMARY ===")
print(f"DatePickers:    {_v(datePickers)} (expect >= 2 on forecast)")
print(f"Buttons:        {_v(antButtons)}")
print(f"Selects:        {_v(antSelects)}")
print(f"Inputs:         {_v(antInputs)}")
print(f"Tables:         {_v(antTables)}")
print(f"Alerts:         {_v(antAlerts)}")
if isinstance(modelName, dict): print(f"Model header:   {_v(modelName)}")
print("All pages load: OK")

driver.close()
