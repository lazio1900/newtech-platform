FROM node:22-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# 빌드 시점에 API base URL을 정적으로 주입.
# - docker-compose 사용: 빈 값 → nginx가 /api 프록시
# - PaaS 분리 배포: 실제 API 도메인 (예: https://api.example.com)
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build


FROM nginx:1.27-alpine AS runtime

# docker-compose 환경에서 nginx가 /api를 backend 컨테이너로 프록시하기 위한 기본값
ENV BACKEND_HOST=backend
ENV BACKEND_PORT=8002

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q --spider http://127.0.0.1/ || exit 1

# nginx alpine 이미지의 기본 entrypoint가 /etc/nginx/templates/*.template 를 envsubst로 렌더링
