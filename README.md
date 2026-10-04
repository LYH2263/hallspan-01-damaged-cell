# HallSpan 考场间距排座

在考室网格上按最小曼哈顿距离排座，同试卷套不得四邻相邻，并输出违规与统计。支持损坏禁坐格：损坏格空白禁坐，剩余可坐格必须四邻连通，否则整场排座失败。

技术栈：Python 3.12 / FastAPI / SQLAlchemy / PostgreSQL / Vue 3 / TypeScript / Vite

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4900 |
| API | http://localhost:9900 |
| API 文档 | http://localhost:9900/docs |
| Postgres | localhost:5450 |

健康检查：`GET http://localhost:9900/api/health`

## 使用说明

1. 在「考室」「考生」「试卷套」确认基础数据。
2. 在「考室」点击格子登记损坏禁坐格并保存；行列越界或重复登记整场拒绝。
3. 打开「排座图」执行间距排座；损坏格空白不落人，若损坏把可坐区域割裂则不增方案、整场失败。
4. 在「违规」查看间距或同卷相邻问题与未排原因。
5. 在「统计」查看占用、损坏格与可坐容量汇总。

## 损坏格接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/damaged?hall_id=1` | 查看损坏名单、可坐容量、连通状态 |
| PUT | `/api/damaged?hall_id=1` | 整单替换名单 `{"cells":[{"row":0,"col":0}]}`；越界/重复 → 400 整场拒绝 |
| GET | `/api/seating/plans?hall_id=1` | 方案列表（割裂失败不增行） |

## 开发与测试

```bash
docker compose exec api pytest -q
```
