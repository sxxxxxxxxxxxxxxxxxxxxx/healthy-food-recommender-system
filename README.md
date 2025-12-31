# 健康食物推荐系统

个性化健康食物推荐系统 - 基于Flask的智能食物推荐应用，支持根据天气、健康状况、过敏史等因素推荐食物。

## 功能特性

- 智能食物推荐：根据天气、时间、健康状况、过敏史、热量限制推荐食物
- 一餐组合推荐：自动搭配主食、蛋白、蔬菜
- 进度追踪：可视化近7天热量/糖分趋势
- 搜索功能：搜索历史餐食和食物库
- 支持Vercel部署

## 技术栈

- 后端：Flask, SQLAlchemy, SQLite
- 前端：原生JavaScript, Chart.js
- 部署：Vercel

## 环境变量

- `OPENWEATHER_API_KEY`: OpenWeatherMap API密钥（必需）
- `UNSPLASH_ACCESS_KEY`: Unsplash API密钥（可选）

## 部署

项目已配置Vercel部署，可直接连接GitHub仓库进行部署。
