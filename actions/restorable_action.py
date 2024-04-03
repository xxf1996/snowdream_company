from metagpt.actions import Action


class RestorableAction(Action):
  finished: bool = False
  """之前动作是否已经完成"""
  need_restore: bool = False
  """是否需要恢复之前的行为"""

  def __init__(self, **kwargs):
    super().__init__(**kwargs)

  def to_restore(self, finished: bool = False):
    self.need_restore = True
    self.finished = finished