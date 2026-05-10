import re

with open("src/price_scanner.py", "r") as f:
    code = f.read()

# Find the items locator and safely inject a 3.5 second wait right before it
patched_code = re.sub(
    r'([ \t]+)(items = page\.locator\("ul li, \[class\*\=\'result\'\], \[class\*\=\'option\'\]"\))',
    r'\1await asyncio.sleep(3.5)  # Wait for Zepto servers to return suggestions\n\1\2',
    code
)

with open("src/price_scanner.py", "w") as f:
    f.write(patched_code)

print("✅ Successfully patched price_scanner.py!")
