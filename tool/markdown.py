import re

def get_lang_content(source: str, lang = "json"):
  pattern = r"```" + lang + "\n(.*?)\n\s*```"
  return re.findall(pattern, source, re.DOTALL)[0]
