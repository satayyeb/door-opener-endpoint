## Door opener endpoint


#### Required environment variables:

- `API_AUTHORIZATION_TOKEN_LIST`
- `ESP_AUTHORIZATION_TOKEN`
- `UPDATE_AUTHORIZATION_TOKEN`
- `SENTRY_DSN`

#### Run:

```shell
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Deploy:

#### Build:

```shell
    docker build --network=host --build-arg HTTP_PROXY=http://0.0.0.0:10809 -t door-opener-endpoint:1.0.0 .
```
#### Run:
```shell
    docker run -p 8000:8000 -v door:/opt/data --env-file local.env --rm door-opener-endpoint:1.0.0
```

