import os
from playwright.async_api import async_playwright

def get_image_path(file_path: str):
  dirname = os.path.dirname(file_path)
  filename = os.path.basename(file_path)
  base, _ = os.path.splitext(filename)

  return os.path.join(dirname, f"{base}.png")

async def generate_screenshots(files: list[str]):
  async with async_playwright() as playwright:
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()

    for file in files:
      await page.goto(f"file://{file}")
      # page.wait_for_timeout(1000)
      imgae_path = get_image_path(file)
      await page.screenshot(path=imgae_path, full_page=True)

    await browser.close()