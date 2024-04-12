import json
import os
from playwright.async_api import async_playwright

def get_image_path(file_path: str):
  dirname = os.path.dirname(file_path)
  filename = os.path.basename(file_path)
  base, _ = os.path.splitext(filename)

  return os.path.join(dirname, f"{base}.png")

def get_file_content(file_path: str):
  with open(file_path, "r", encoding="utf-8") as file:
    return file.read()

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

async def generate_vue_element_screenshots(files: list[str], imports: list[str]):
  async with async_playwright() as playwright:
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()
    import_map: dict[str, str] = {}

    for pck in imports:
      import_map[pck] = f"https://cdn.jsdelivr.net/npm/{pck}"

    map_content = json.dumps({
      imports: import_map
    })
    import_map_json: str = await page.evaluate(f"window.encodeURIComponent(`{map_content}`)")

    for file in files:
      file_content = get_file_content(file)
      code: str = await page.evaluate(f"window.encodeURIComponent(`{file_content}`)")
      await page.goto(f"https://localhost:5173/?code={code}&map={import_map_json}")
      await page.wait_for_load_state("domcontentloaded")
      await page.wait_for_timeout(5000)
      imgae_path = get_image_path(file)
      await page.screenshot(path=imgae_path, full_page=True)

    await browser.close()