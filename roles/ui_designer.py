# UI设计师
import json
import os
from typing import Any
from metagpt.schema import Message
from snowdream_company.roles.restorable_role import RestorableRole
from snowdream_company.roles.demand_analyst import DemandAnalysis, DemandChange, DemandConfirmationAsk, DemandConfirmationAnswer
from snowdream_company.actions.restorable_action import RestorableAction
from metagpt.logs import logger
from snowdream_company.tool.browser import generate_screenshots
from snowdream_company.tool.markdown import get_html_comment, get_lang_content
from snowdream_company.tool.type import is_same_action

class UIAnalysis(RestorableAction):
  name: str = "UIAnalysis"
  SYSTEM_TEMPLATE: str = """{system}
  这里有一份来自产品经理同事发布的需求文档（三个反引号之间）：```{doc}```。
  """
  PROMPT_TEMPLATE: str = """
  根据需求文档，你需要从中提取出你自己的工作任务（即UI设计师需要做的事情）。根据你的任务，完成相应具有尽可能多细节的UI设计稿，要确保给出的设计稿可以让web前端开发同事进行直接使用；请用html+css的格式进行设计，并不要求你实现最终的功能代码，你只需要用html+css进行样式的设计即可！可以根据需要拆分不同的模块进行设计，每个模块需要用一个单独的html代码块（对应模块的css样式也包含在html代码块之中！）来表示，并在html代码块第一行中用注释标注出该模块的作用和模块名称。

  请注意不是简单的把需求文档加上样式！确保设计稿的内容是清晰且没有重复的！请务必确保不要出现单独的css代码块，所有的css样式（包括css动画）务必应用到具体的html元素上！

  如果有需要设计图片的任务，请用详细的文字描述出该图片的内容及尺寸等细节信息，并用markdown代码块将这段文字进行包裹，代码块语言设置为generate-image；每一个图片的描述用一个单独的generate-image代码块进行表示。以下是一个满足上述格式的回答示例，你可以参照这个格式进行回答：

  ```html
  <!-- 模块名称和描述 -->
  <div>该模块的布局结构</div>
  ...
  <style>
  /** 该模块的样式和动画 */
  ...
  </style>
  ```

  ```html
  <!-- 模块名称和描述 -->
  <div>该模块的布局结构</div>
  ...
  <style>
  /** 该模块的样式和动画 */
  ...
  </style>
  ```

  ```generate-image
  关于图片的描述信息
  ...
  ```

  ```generate-image
  关于图片的描述信息
  ...
  ```
  """

  async def run(self, role: RestorableRole):
    last_msg = role.rc.memory.get(k=1)[0]
    if self.need_restore and self.finished:
      return last_msg.content

    info: dict[str, Any] = json.loads(last_msg.content)
    demand_json = info["demands"]
    system_prompt = self.SYSTEM_TEMPLATE.format(system=role.get_system_msg(), doc=demand_json)
    prompt = self.PROMPT_TEMPLATE

    answer = await self.llm.aask(
      system_msgs=[system_prompt],
      msg=prompt
    )

    await self.save_ui(role.get_project_path(), answer)

    return answer

  async def save_ui(self, project_path: str, answer: str):
    ui_list: list[str] = get_lang_content(answer, is_all=True, lang="html")
    html_paths: list[str] = []
    # TODO: 图片资源生成&人机对话确认
    for ui in ui_list:
      name: str = get_html_comment(ui)
      ui_path = os.path.join(project_path, "ui", "1.0.0", f"{name}.html")
      html_paths.append(ui_path)
      with open(ui_path, "w", encoding="utf-8") as f:
        f.write(ui)
    await generate_screenshots(html_paths)



class UIDesigner(RestorableRole):
  name: str = "斯蒂芬"
  profile: str = "ui designer"
  goal: str = "基于同事提供的需求为其提供相应的且合理的UI设计"

  def __init__(self, **kwargs):
    super().__init__(**kwargs)
    self.set_actions([DemandConfirmationAsk, UIAnalysis])
    self._set_react_mode(react_mode="react", max_react_loop=999)
    self.set_watch([DemandAnalysis, DemandConfirmationAnswer, DemandChange])

  def state_machine(self):
    msg = self.get_memories(k=1)[0]

    if is_same_action(msg.cause_by, str(DemandAnalysis)):
      return self.get_action(DemandConfirmationAsk) # FIXME: 搞不懂这里之前没用实例为啥也可以？

    if is_same_action(msg.cause_by, str(DemandConfirmationAnswer)) and self.name in msg.send_to:
      return self.get_action(DemandConfirmationAsk)

    if is_same_action(msg.cause_by, str(DemandChange)) and self.name in msg.send_to:
      return self.get_action(UIAnalysis)

    return None

  async def _act(self) -> Message:
    # TODO: 标准化act流程
    logger.info(f"{self._setting}: to do {self.rc.todo}({self.rc.todo.name})")
    todo = self.rc.todo
    msg = self.get_memories(k=1)[0]
    answer = ''
    self.update_state(todo)

    if isinstance(todo, DemandConfirmationAsk):
      answer = await todo.run(self)
    elif isinstance(todo, UIAnalysis):
      answer = await todo.run(self)
    else:
      answer = await todo.run(msg.content)

    record = Message(content=answer, role=self.profile, cause_by=type(todo))
    self.update_state(todo, True)
    # NOTICE: 仅正在恢复行为且之前行为已经结束的时候不需要保存记忆（因为之前记忆已经存在了）
    if not self.restoring_action or not todo.finished:
      record = self.add_memory(record)

    if isinstance(todo, RestorableAction):
      self.restoring_action = False
      self.need_restore_action = False
      RestorableRole.restorable = False # 恢复完成
      todo.finished = False
      todo.need_restore = False

    return record