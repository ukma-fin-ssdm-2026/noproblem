# Сирі метрики запусків CI/CD

Усі 90 запусків на `main` з історії GitHub Actions за 21.10–17.11.2026: workflow `CI` і `Generate and Deploy API Docs` (у таблиці — «API Docs»). Час наведено в Europe/Kyiv. Черга — від `createdAt` запуску до найранішого `startedAt` його завдань; виконання — від найранішого `startedAt` до найпізнішого `completedAt`. Хвилини округлено до цілих. Дані зібрано скриптом `scripts/collect_ci_metrics.py`, таблицю згенеровано `scripts/compute_dora.py`.

| № | Коміт | Workflow | PR | Перший коміт PR | Запуск завершено | Черга, хв | Виконання, хв | Статус | Примітка |
|---:|---|---|---:|---|---|---:|---:|:---:|---|
| 1 | `4f526ee` | CI | [#173](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/173) | 21.10 20:21 | 21.10 20:37 | 0 | 1 | ✅ |  |
| 2 | `61cc158` | CI | [#175](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/175) | 21.10 21:54 | 21.10 22:21 | 0 | 1 | ✅ |  |
| 3 | `198e01a` | CI | [#174](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/174) | 21.10 21:16 | 21.10 23:35 | 0 | 1 | ✅ |  |
| 4 | `74953d7` | CI | [#176](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/176) | 21.10 23:25 | 21.10 23:35 | 0 | 1 | ✅ |  |
| 5 | `406bc4b` | CI | [#177](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/177) | 23.10 10:24 | 23.10 10:26 | 0 | 1 | ✅ |  |
| 6 | `82f0b94` | CI | [#178](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/178) | 23.10 10:34 | 23.10 10:37 | 0 | 1 | ✅ |  |
| 7 | `f80935e` | CI | [#180](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/180) | 24.10 10:07 | 26.10 10:39 | 0 | 1 | ✅ |  |
| 8 | `f80935e` | API Docs | [#180](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/180) | 24.10 10:07 | 26.10 10:39 | 1 | 1 | ✅ |  |
| 9 | `1e49303` | CI | [#181](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/181) | 26.10 10:52 | 26.10 11:28 | 0 | 1 | ✅ |  |
| 10 | `7f9125c` | CI | [#182](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/182) | 26.10 11:50 | 26.10 12:01 | 0 | 1 | ✅ |  |
| 11 | `7c35348` | CI | [#184](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/184) | 26.10 13:18 | 26.10 14:48 | 0 | 1 | ✅ |  |
| 12 | `c3280c9` | API Docs | [#185](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/185) | 26.10 14:44 | 26.10 17:19 | 0 | 1 | ✅ |  |
| 13 | `c3280c9` | CI | [#185](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/185) | 26.10 14:44 | 26.10 17:20 | 0 | 1 | ✅ |  |
| 14 | `447b568` | API Docs | [#187](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/187) | 26.10 20:10 | 27.10 12:44 | 0 | 1 | ✅ |  |
| 15 | `447b568` | CI | [#187](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/187) | 26.10 20:10 | 27.10 12:44 | 0 | 1 | ✅ |  |
| 16 | `0905893` | API Docs | [#188](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/188) | 27.10 13:15 | 27.10 14:11 | 0 | 1 | ✅ |  |
| 17 | `0905893` | CI | [#188](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/188) | 27.10 13:15 | 27.10 14:12 | 0 | 1 | ✅ |  |
| 18 | `65f7b4b` | CI | [#190](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/190) | 27.10 15:15 | 27.10 18:10 | 0 | 1 | ✅ |  |
| 19 | `65f7b4b` | API Docs | [#190](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/190) | 27.10 15:15 | 27.10 18:10 | 0 | 1 | ✅ |  |
| 20 | `9685a19` | CI | [#189](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/189) | 27.10 14:42 | 27.10 18:10 | 0 | 1 | ✅ |  |
| 21 | `e54a0b2` | CI | [#198](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/198) | 27.10 19:07 | 27.10 19:15 | 0 | 1 | ✅ |  |
| 22 | `c3a12dc` | CI | [#199](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/199) | 28.10 11:45 | 28.10 12:00 | 0 | 1 | ✅ |  |
| 23 | `a177dea` | CI | [#201](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/201) | 28.10 12:13 | 28.10 12:58 | 0 | 1 | ✅ |  |
| 24 | `19da8fb` | CI | [#200](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/200) | 28.10 12:09 | 28.10 12:58 | 0 | 1 | ✅ |  |
| 25 | `fe2a30c` | CI | [#203](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/203) | 27.10 19:23 | 28.10 17:29 | 0 | 1 | ✅ |  |
| 26 | `fe2a30c` | API Docs | [#203](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/203) | 27.10 19:23 | 28.10 17:29 | 0 | 1 | ✅ |  |
| 27 | `9198038` | API Docs | [#204](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/204) | 28.10 17:39 | 28.10 17:44 | 0 | 1 | ✅ |  |
| 28 | `9198038` | CI | [#204](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/204) | 28.10 17:39 | 28.10 17:44 | 0 | 1 | ✅ |  |
| 29 | `d7f155f` | API Docs | [#206](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/206) | 28.10 17:46 | 28.10 19:11 | 0 | 1 | ❌ | впав крок: Fail if committed spec is stale; закомічена OpenAPI-специфікація не збіглася зі згенерованою |
| 30 | `d7f155f` | CI | [#206](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/206) | 28.10 17:46 | 28.10 19:12 | 0 | 1 | ✅ |  |
| 31 | `74e8487` | CI | [#207](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/207) | 28.10 18:40 | 28.10 19:19 | 0 | 1 | ✅ |  |
| 32 | `367217e` | CI | [#208](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/208) | 28.10 19:10 | 28.10 19:20 | 0 | 1 | ✅ |  |
| 33 | `357cafd` | CI | [#209](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/209) | 28.10 19:21 | 28.10 19:26 | 0 | 1 | ✅ |  |
| 34 | `e36ff3d` | CI | [#211](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/211) | 28.10 21:08 | 28.10 21:21 | 0 | 1 | ✅ |  |
| 35 | `a30792a` | API Docs | [#210](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/210) | 28.10 19:55 | 28.10 21:22 | 1 | 1 | ✅ |  |
| 36 | `a30792a` | CI | [#210](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/210) | 28.10 19:55 | 28.10 21:24 | 3 | 1 | ✅ |  |
| 37 | `dc0ed4e` | CI | [#214](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/214) | 30.10 10:39 | 30.10 14:33 | 18 | 2 | ✅ |  |
| 38 | `dc0ed4e` | API Docs | [#214](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/214) | 30.10 10:39 | 30.10 14:21 | 5 | 1 | ✅ |  |
| 39 | `71d715d` | CI | [#212](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/212) | 30.10 10:17 | 30.10 16:23 | 6 | 2 | ✅ |  |
| 40 | `4e1f6bd` | CI | [#218](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/218) | 30.10 16:07 | 31.10 12:07 | 0 | 1 | ✅ |  |
| 41 | `59bd1bd` | API Docs | [#221](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/221) | 31.10 10:50 | 31.10 12:38 | 0 | 1 | ✅ |  |
| 42 | `59bd1bd` | CI | [#221](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/221) | 31.10 10:50 | 31.10 12:39 | 0 | 1 | ✅ |  |
| 43 | `15153c7` | CI | [#222](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/222) | 31.10 19:10 | 31.10 21:48 | 0 | 1 | ✅ |  |
| 44 | `b81b2ed` | CI | [#225](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/225) | 31.10 21:09 | 01.11 09:46 | 0 | 1 | ✅ |  |
| 45 | `474388f` | CI | [#226](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/226) | 01.11 08:35 | 01.11 09:46 | 0 | 1 | ✅ |  |
| 46 | `7aa3790` | CI | [#227](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/227) | 01.11 10:16 | 01.11 14:38 | 7 | 1 | ✅ |  |
| 47 | `a9854b3` | CI | [#228](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/228) | 01.11 16:55 | 01.11 17:21 | 12 | 1 | ✅ |  |
| 48 | `fb5c167` | CI | [#229](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/229) | 01.11 17:50 | 01.11 18:28 | 6 | 1 | ✅ |  |
| 49 | `045fa33` | CI | [#232](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/232) | 03.11 16:13 | 03.11 17:01 | 0 | 1 | ✅ |  |
| 50 | `d453100` | CI | [#233](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/233) | 03.11 17:03 | 03.11 17:10 | 0 | 1 | ✅ |  |
| 51 | `3e1cb84` | CI | [#234](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/234) | 03.11 17:32 | 03.11 21:11 | 0 | 1 | ✅ |  |
| 52 | `25e6ed1` | CI | [#241](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/241) | 04.11 11:19 | 04.11 17:56 | 0 | 1 | ✅ |  |
| 53 | `25e6ed1` | API Docs | [#241](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/241) | 04.11 11:19 | 04.11 18:17 | 21 | 1 | ✅ |  |
| 54 | `d1cd719` | CI | [#244](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/244) | 04.11 17:49 | 04.11 18:14 | 0 | 1 | ✅ |  |
| 55 | `5ab07a6` | CI | [#245](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/245) | 04.11 18:08 | 04.11 18:37 | 0 | 1 | ✅ |  |
| 56 | `6401f9e` | CI | [#246](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/246) | 04.11 18:23 | 04.11 18:37 | 0 | 1 | ✅ |  |
| 57 | `1bef69f` | CI | [#247](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/247) | 04.11 18:46 | 04.11 18:58 | 1 | 1 | ✅ |  |
| 58 | `f8fa3eb` | CI | [#250](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/250) | 04.11 20:45 | 04.11 20:54 | 3 | 1 | ✅ |  |
| 59 | `c0286f9` | CI | [#248](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/248) | 04.11 19:19 | 04.11 20:57 | 1 | 2 | ✅ |  |
| 60 | `4561b8c` | CI | [#249](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/249) | 04.11 20:44 | 04.11 20:58 | 1 | 1 | ✅ |  |
| 61 | `dbe98b7` | CI | [#251](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/251) | 04.11 22:47 | 04.11 22:58 | 0 | 1 | ✅ |  |
| 62 | `8d1e0fa` | CI | [#252](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/252) | 06.11 10:20 | 06.11 10:24 | 0 | 1 | ✅ |  |
| 63 | `e998684` | CI | [#253](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/253) | 06.11 10:37 | 06.11 10:44 | 1 | 1 | ✅ |  |
| 64 | `d2a8a79` | API Docs | [#255](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/255) | 08.11 00:19 | 08.11 12:04 | 0 | 1 | ❌ | впав крок: Setup Python; HTTP 504 під час завантаження Python |
| 65 | `d2a8a79` | CI | [#255](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/255) | 08.11 00:19 | 08.11 12:05 | 0 | 2 | ✅ |  |
| 66 | `9e6bd9c` | CI | [#256](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/256) | 08.11 12:13 | 08.11 13:55 | 0 | 1 | ✅ |  |
| 67 | `fe3ea01` | CI | [#258](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/258) | 09.11 14:18 | 09.11 17:39 | 0 | 1 | ✅ |  |
| 68 | `fe3ea01` | API Docs | [#258](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/258) | 09.11 14:18 | 09.11 17:40 | 0 | 2 | ⚪ | скасовано; не рахується як збій зміни |
| 69 | `c538dd6` | API Docs | [#259](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/259) | 09.11 17:31 | 09.11 17:44 | 0 | 4 | ✅ |  |
| 70 | `c538dd6` | CI | [#259](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/259) | 09.11 17:31 | 09.11 17:41 | 0 | 1 | ✅ |  |
| 71 | `eb3ef71` | API Docs | [#261](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/261) | 09.11 19:12 | 10.11 13:54 | 0 | 1 | ✅ |  |
| 72 | `eb3ef71` | CI | [#261](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/261) | 09.11 19:12 | 10.11 13:55 | 0 | 1 | ✅ |  |
| 73 | `53b8810` | API Docs | [#262](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/262) | 10.11 14:12 | 10.11 14:16 | 0 | 1 | ✅ |  |
| 74 | `53b8810` | CI | [#262](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/262) | 10.11 14:12 | 10.11 14:17 | 0 | 1 | ✅ |  |
| 75 | `0bb61f2` | CI | [#263](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/263) | 10.11 16:41 | 10.11 16:47 | 0 | 1 | ✅ |  |
| 76 | `731af30` | CI | [#264](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/264) | 10.11 17:09 | 10.11 17:30 | 0 | 1 | ✅ |  |
| 77 | `75f8e59` | CI | [#266](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/266) | 11.11 17:23 | 11.11 17:37 | 0 | 1 | ✅ |  |
| 78 | `1e6cf3c` | CI | [#267](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/267) | 11.11 18:11 | 11.11 18:29 | 0 | 1 | ✅ |  |
| 79 | `3261b06` | CI | [#268](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/268) | 11.11 18:51 | 11.11 21:46 | 0 | 3 | ✅ |  |
| 80 | `6a5513e` | CI | [#269](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/269) | 11.11 18:46 | 11.11 21:48 | 0 | 3 | ✅ |  |
| 81 | `331fe98` | CI | [#270](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/270) | 11.11 21:50 | 12.11 08:45 | 1 | 1 | ✅ |  |
| 82 | `4d8822a` | CI | [#271](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/271) | 13.11 10:35 | 13.11 10:43 | 0 | 1 | ✅ |  |
| 83 | `e0c8486` | CI | [#272](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/272) | 13.11 16:12 | 13.11 16:31 | 0 | 1 | ✅ |  |
| 84 | `c054b48` | API Docs | [#274](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/274) | 16.11 16:00 | 16.11 16:08 | 0 | 1 | ✅ |  |
| 85 | `c054b48` | CI | [#274](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/274) | 16.11 16:00 | 16.11 16:09 | 0 | 1 | ✅ |  |
| 86 | `bba4327` | CI | [#275](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/275) | 17.11 13:42 | 17.11 13:46 | 0 | 1 | ✅ |  |
| 87 | `26b235b` | API Docs | [#276](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/276) | 16.11 16:47 | 17.11 15:19 | 0 | 1 | ✅ |  |
| 88 | `26b235b` | CI | [#276](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/276) | 16.11 16:47 | 17.11 15:20 | 0 | 1 | ✅ |  |
| 89 | `818e093` | CI | [#277](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/277) | 17.11 15:30 | 17.11 15:37 | 0 | 1 | ✅ |  |
| 90 | `0ec1ec3` | CI | [#278](https://github.com/ukma-fin-ssdm-2026/noproblem/pull/278) | 17.11 16:20 | 17.11 16:24 | 0 | 1 | ✅ |  |

✅ успішний · ❌ невдалий · ⚪ скасований.

## File was created by Claude, verified and modified by team ##
