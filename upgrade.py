import re

with open("src/price_scanner.py", "r") as f:
    code = f.read()

# 1. Remove the dumb 3.5s wait
code = re.sub(r'[ \t]+await asyncio\.sleep\(3\.5\).*?\n', '\n', code)

# 2. Inject the Smart Wait and Keyboard Enter Press
code = re.sub(
    r'([ \t]+)(items = page\.locator\("ul li, \[class\*=\'result\'\], \[class\*=\'option\'\]"\))',
    r'\1# Smart Wait & Keyboard Press\n\1try:\n\1    await page.locator("ul li, [class*=\'result\'], [class*=\'option\']").first.wait_for(state="visible", timeout=4000)\n\1    await page.keyboard.press("Enter")\n\1except Exception:\n\1    pass\n\1\2',
    code
)

with open("src/price_scanner.py", "w") as f:
    f.write(code)

print("✅ Upgraded: Added Smart Waits and Keyboard Auto-Clicking!")
