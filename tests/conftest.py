# -*- coding: utf-8 -*-
"""
pytest 根配置：将项目根加入 path，便于直接 import 各模块。
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.chdir(_ROOT)
