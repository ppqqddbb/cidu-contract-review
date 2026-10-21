# 本地PostgreSQL

```powershell
docker compose -f deploy/compose/docker-compose.yml up -d
docker compose -f deploy/compose/docker-compose.yml ps
```

默认密码仅用于本机开发。试用环境必须通过安全配置注入真实密码，且不得暴露数据库端口到公网。
