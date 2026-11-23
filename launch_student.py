# -*- coding: utf-8 -*-
"""学生机启动器：显示连接设置并启动可见的课堂管理客户端。"""

from __future__ import print_function

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(str(ROOT))


def main():
    from student.client import main as student_main
    student_main(list(sys.argv[1:]))


if __name__ == "__main__":
    main()
