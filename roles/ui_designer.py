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
from pathvalidate import sanitize_filename

from snowdream_company.tool.ui import get_user_input

class UIAnalysis(RestorableAction):
  name: str = "UIAnalysis"
  SYSTEM_TEMPLATE: str = """{system}
  这里有一份来自产品经理同事发布的需求文档（三个反引号之间）：```{doc}```。
  """
  # TODO: 最好结合需求沟通记录？因为需求沟通的结果看起来细节蛮多的……
  PROMPT_TEMPLATE: str = """
  我把调整好的需求文档发给你了，你需要从需求文档和我们的对话记录中提取出你自己的工作任务（即UI设计师需要做的事情），每个任务用单独的task代码块进行表示；根据你整理得到的任务，完成相应任务的UI设计稿，要确保给出的设计稿可以让web前端开发同事进行直接使用；请用html+css的格式进行设计，并不要求你实现最终的功能代码，你只需要用html+css进行样式的设计即可！可以根据需要拆分不同的模块进行设计，每个模块需要用一个单独的html代码块（对应模块的css样式也包含在html代码块之中！）来表示，并在html代码块第一行中用注释标注出该模块的作用和模块名称。

  请注意不是简单的把需求文档加上样式！确保设计稿的内容是清晰且没有重复的！请务必确保不要出现单独的css代码块，所有的css样式（包括css动画）务必应用到具体的html元素上！

  如果有需要设计图片的任务，请用详细的文字描述出该图片的文件名、内容、风格及尺寸等细节信息，并用markdown代码块将这段文字进行包裹，代码块语言设置为generate-image；每一个图片的描述用一个单独的generate-image代码块进行表示。

  最后请检查所有任务是否已经完成，按照markdown的任务列表语法整理出任务的完成情况；以下是一个满足上述格式的回答示例，你可以参照这个格式进行回答：

  ```task
  task1: 任务的详细描述
  ```

  ```task
  task2: 任务的详细描述
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
  图片名字.png
  关于图片的描述信息
  ...
  ```

  ```generate-image
  图片名字.png
  关于图片的描述信息
  ...
  ```

  - [ ]: task1
  - [x]: task2
  ...
  - [x]: taskN
  """

  async def run(self, role: RestorableRole):
    last_msg = role.rc.memory.get(k=1)[0]
    if self.need_restore and self.finished:
      return last_msg.content

    if self.need_restore:
      res: Message = await self.restore(role)
      return res

    info: dict[str, Any] = json.loads(last_msg.content)
    demand_json = info["demands"]
    system_prompt = self.SYSTEM_TEMPLATE.format(system=role.get_system_msg(), doc=demand_json)
    history = self.get_demand_history(role.rc.memory.get(), last_msg.sent_from)

    answer = await self.llm.aask(
      system_msgs=[system_prompt],
      msg=history
    )

    await self.save_ui(role.get_project_path(), answer)
    # 这算是初稿
    draft_msg = Message(content=answer, role=role.profile, cause_by=self._get_draft_type())
    role.add_memory(draft_msg)
    res = await self.get_user_answer(role, answer)

    return res

  async def restore(self, role: RestorableRole):
    last_msg = role.rc.memory.get(k=1)[0]
    logger.info(last_msg.content)
    if is_same_action(last_msg.cause_by, self._get_draft_type()):
      await self.save_ui(role.get_project_path(), last_msg.content)
      res = await self.get_user_answer(role)
      return res
    res = await self.get_ui_draft(role)
    return res

  async def get_user_answer(self, role: RestorableRole) -> Message:
    user_answer = get_user_input("UI审核意见", "你的修改意见（end代表没有修改意见了）：")
    if user_answer == "end":
      return role.rc.memory.get(k=1)[0]

    content = f"{user_answer}。请根据我的修改意见在之前的基础上重新设计UI，并按照上面约定的格式给出修改后的完整UI设计稿（即要包含没有改动的部分！）。"
    user_msg = Message(content=content, role="user", cause_by=self._get_user_answer_type())
    role.add_memory(user_msg)
    res = await self.get_ui_draft(role)

    return res

  async def get_ui_draft(self, role: RestorableRole):
    histroy = self.get_comunication_history(role.rc.memory.get())
    system_prompt = self.get_system_prompt(role)

    answer = await self.llm.aask(
      system_msgs=[system_prompt],
      msg=histroy
    )

    await self.save_ui(role.get_project_path(), answer)

    draft_msg = Message(content=answer, role=role.profile, cause_by=self._get_draft_type())
    role.add_memory(draft_msg)

    res = await self.get_user_answer(role)

    return res


  async def save_ui(self, project_path: str, answer: str):
    self.clear_ui(project_path)
    ui_list: list[str] = get_lang_content(answer, is_all=True, lang="html")
    html_paths: list[str] = []
    # TODO: 图片资源生成
    for ui in ui_list:
      name: str = sanitize_filename(get_html_comment(ui), replacement_text="_") # NOTICE: 确保文件名是合法的！
      ui_path = os.path.join(project_path, "ui", "1.0.0", f"{name}.html")
      html_paths.append(ui_path)
      with open(ui_path, "w", encoding="utf-8") as f:
        f.write(ui)
    await generate_screenshots(html_paths)

  def clear_ui(self, project_path: str):
    directory = os.path.join(project_path, "ui", "1.0.0")
    if not os.path.exists(directory):
      return

    for filename in os.listdir(directory):
      file_path = os.path.join(directory, filename)
      if os.path.isfile(file_path):
        os.remove(file_path)

  def get_demand_history(self, messages: list[Message], sent_from: str):
    records: list[dict[str, str]] = [
      {
        "role": "user",
        "content": "你对需求列表有什么疑问吗？"
      }
    ]
    for message in messages:
      if is_same_action(message.cause_by, str(DemandConfirmationAsk)):
        records.append({
          "role": "assistant",
          "content": message.content
        })
      if is_same_action(message.cause_by, str(DemandConfirmationAnswer)) and message.sent_from == sent_from:
        records.append({
          "role": "user",
          "content": message.content
        })

    if records[-1]["content"] == "end":
      records = records[:-2]

    records.append({
      "role": "user",
      "content": self.PROMPT_TEMPLATE
    })

    return records

  def get_comunication_history(self, messages: list[Message]):
    records: list[dict[str, str]] = [
      {
        "role": "user",
        "content": self.PROMPT_TEMPLATE
      }
    ]
    drafts: list[Message] = []
    user_msgs: list[Message] = []
    for message in messages:
      if is_same_action(message.cause_by, self._get_draft_type()):
        drafts.append(message)
      if is_same_action(message.cause_by, self._get_user_answer_type()):
        user_msgs.append(message)

    records.append({
      "role": "assistant",
      "content": drafts[-1].content
    })
    records.append({
      "role": "user",
      "content": user_msgs[-1].content
    })

    return records

  def get_demand_change(self, role: RestorableRole):
    messages = role.rc.memory.get()
    related_msgs: list[Message] = []
    for message in messages:
      if is_same_action(message.cause_by, str(DemandChange)):
        related_msgs.append(message)

    return related_msgs[-1]

  def get_system_prompt(self, role: RestorableRole):
    demand_change_msg = self.get_demand_change(role)
    info: dict[str, Any] = json.loads(demand_change_msg.content)
    demand_json = info["demands"]
    system_prompt = self.SYSTEM_TEMPLATE.format(system=role.get_system_msg(), doc=demand_json)

    return system_prompt


  def _get_draft_type(self):
    return f"{type(self)}_ui_draft"

  def _get_user_answer_type(self):
    return f"{type(self)}_user_answer"


class UIDesigner(RestorableRole):
  name: str = "斯蒂芬"
  profile: str = "ui designer"
  goal: str = "基于同事提供的需求为其提供相应的且合理的UI设计"

  def __init__(self, **kwargs):
    super().__init__(**kwargs)
    self.focus = "UI设计、交互设计和用户体验"
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

    if self.restoring_action and todo.finished:
      record = msg # TODO: 事实上所有恢复的已结束动作直接返回消息即可，无需再执行动作？
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