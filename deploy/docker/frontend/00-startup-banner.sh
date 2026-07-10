#!/bin/sh
PUBLISHED="${FRONTEND_PUBLIC:-127.0.0.1:${FRONTEND_PORT:-8082}->80}"
WEBAPP_API_BASE_URL_VALUE="${WEBAPP_API_BASE_URL:-/api}"
WEBAPP_BACKEND_UPSTREAM="${WEBAPP_BACKEND_UPSTREAM:-http://backend:8081}"
WEBAPP_BACKEND_UPSTREAM_HOST_VALUE="${WEBAPP_BACKEND_UPSTREAM_HOST:-}"
if [ -z "$WEBAPP_BACKEND_UPSTREAM_HOST_VALUE" ]; then
  WEBAPP_BACKEND_UPSTREAM_HOST_VALUE="$(
    printf '%s' "$WEBAPP_BACKEND_UPSTREAM" \
      | sed -n 's#^[A-Za-z][A-Za-z0-9+.-]*://\([^/:]*\).*#\1#p'
  )"
fi
WEBAPP_BACKEND_UPSTREAM_HOST_VALUE="${WEBAPP_BACKEND_UPSTREAM_HOST_VALUE:-backend}"
MINISHOP_EDGE_TOKEN_HEADER_VALUE="${MINISHOP_EDGE_TOKEN_HEADER:-X-Minishop-Edge-Token}"
MINISHOP_EDGE_TOKEN_VALUE="${MINISHOP_EDGE_TOKEN:-}"
EDGE_TOKEN_STATUS="disabled"
if [ -n "$MINISHOP_EDGE_TOKEN_VALUE" ]; then
  EDGE_TOKEN_STATUS="enabled"
fi
IMAGE_TAG_VALUE="${IMAGE_TAG:-local}"
BUILD_TAG="${REMNAWAVE_MINISHOP_TAG:-${GIT_TAG:-${BUILD_TAG:-}}}"
if [ -z "$BUILD_TAG" ] && [ -r /build-tag ]; then
  BUILD_TAG="$(cat /build-tag)"
fi
BUILD_TAG="${BUILD_TAG:-unknown}"
BUILD_COMMIT="${REMNAWAVE_MINISHOP_COMMIT:-${GIT_COMMIT:-${COMMIT_SHA:-}}}"
if [ -z "$BUILD_COMMIT" ] && [ -r /build-commit ]; then
  BUILD_COMMIT="$(cat /build-commit)"
fi
BUILD_COMMIT="${BUILD_COMMIT:-unknown}"
DISPLAY_IMAGE_TAG="$IMAGE_TAG_VALUE"
if [ "$IMAGE_TAG_VALUE" = "latest" ] && [ "$BUILD_TAG" != "unknown" ]; then
  DISPLAY_IMAGE_TAG="latest-${BUILD_TAG}"
elif [ "$IMAGE_TAG_VALUE" = "dev" ]; then
  if [ "$BUILD_TAG" != "unknown" ] && [ "$BUILD_COMMIT" != "unknown" ]; then
    DISPLAY_IMAGE_TAG="dev-${BUILD_TAG}+${BUILD_COMMIT}"
  elif [ "$BUILD_TAG" != "unknown" ]; then
    DISPLAY_IMAGE_TAG="dev-${BUILD_TAG}"
  elif [ "$BUILD_COMMIT" != "unknown" ]; then
    DISPLAY_IMAGE_TAG="dev+${BUILD_COMMIT}"
  fi
fi

export WEBAPP_BACKEND_UPSTREAM
export WEBAPP_BACKEND_UPSTREAM_HOST_VALUE
export MINISHOP_EDGE_TOKEN_HEADER_VALUE
export MINISHOP_EDGE_TOKEN_VALUE

NGINX_TEMPLATE_PATH="/etc/nginx/minishop/default.conf.template"
NGINX_CONFIG_PATH="/etc/nginx/conf.d/default.conf"
envsubst '${WEBAPP_BACKEND_UPSTREAM} ${WEBAPP_BACKEND_UPSTREAM_HOST_VALUE} ${MINISHOP_EDGE_TOKEN_HEADER_VALUE} ${MINISHOP_EDGE_TOKEN_VALUE}' \
  < "$NGINX_TEMPLATE_PATH" > "$NGINX_CONFIG_PATH"

cat <<EOF

              ~ ~ ~  r e m n a w a v e  ~ ~ ~

  ███╗   ███╗██╗███╗   ██╗██╗███████╗██╗  ██╗ ██████╗ ██████╗
  ████╗ ████║██║████╗  ██║██║██╔════╝██║  ██║██╔═══██╗██╔══██╗
  ██╔████╔██║██║██╔██╗ ██║██║███████╗███████║██║   ██║██████╔╝
  ██║╚██╔╝██║██║██║╚██╗██║██║╚════██║██╔══██║██║   ██║██╔═══╝
  ██║ ╚═╝ ██║██║██║ ╚████║██║███████║██║  ██║╚██████╔╝██║
  ╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝

              container :: FRONTEND
              image tag :: ${DISPLAY_IMAGE_TAG}
              commit :: ${BUILD_COMMIT}
              listen :: :80
              published :: ${PUBLISHED}
              api base :: ${WEBAPP_API_BASE_URL_VALUE}
              upstream :: ${WEBAPP_BACKEND_UPSTREAM}
        upstream host :: ${WEBAPP_BACKEND_UPSTREAM_HOST_VALUE}
           edge token :: ${EDGE_TOKEN_STATUS}
              healthcheck :: /health
         https://github.com/3252a8/remnawave-minishop

EOF
