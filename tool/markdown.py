import re
from typing import Any

def get_lang_content(source: str, lang = "json", is_all = False):
  pattern = r"```" + lang + "\n(.*?)\n\s*```"

  if is_all:
    return re.findall(pattern, source, re.DOTALL)

  return re.findall(pattern, source, re.DOTALL)[0]

def get_html_comment(source: str):
  return re.findall(r"<!--\s*([^<>]*?)\s*-->", source, re.DOTALL)[0]

def demands_to_markdown(demands: list[dict[str, Any]], parent_level: int = 0) -> str:
  """
  Generate a Markdown representation of demands and their details.

  Parameters:
    demands (list[dict[str, Any]]): A list of demands, where each demand is a dictionary containing keys like '标题', '优先级', '需求描述', and '子需求'.
    parent_level (int, optional): The parent level of demands, defaults to 0.

  Returns:
    str: A Markdown representation of the demands and their details.
  """
  cur_level = parent_level + 1
  res: list[str] = []
  for demand in demands:
    title = f"{'#' * cur_level} {demand['标题']}（优先级：{demand['优先级']}）"
    desc = f"{demand['需求描述']}"
    content = f"{title}\n\n{desc}"

    if "子需求" in demand:
      content += "\n\n" + demands_to_markdown(demand["子需求"], cur_level)

    res.append(content)

  return "\n\n".join(res)

