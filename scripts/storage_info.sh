#!/bin/bash
# 各種ストレージインターフェースの情報をまとめて表示する
system_profiler SPNVMeDataType \
  && system_profiler SPSerialATADataType \
  && system_profiler SPUSBDataType \
  && system_profiler SPThunderboltDataType
