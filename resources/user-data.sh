#!/bin/bash
set -euxo pipefail

# 0) 로그 파일 생성
sudo mkdir -p /var/log/planit/was /var/log/planit/ai
sudo chmod 777 /var/log/planit/was /var/log/planit/ai

# 1) cw 설정 파일
sudo tee /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json > /dev/null <<'EOF'
{
  "agent": {
    "metrics_collection_interval": 60,
    "region": "ap-northeast-2",
    "run_as_user": "root"
  },
  "logs": {
    "force_flush_interval": 5,
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/planit/was/*.log",
            "log_group_name": "/planit/v2/was",
            "log_stream_name": "was-{hostname}-{instance_id}",
            "timezone": "Local",
            "multi_line_start_pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
          },
          {
            "file_path": "/var/log/planit/ai/*.log",
            "log_group_name": "/planit/v2/ai",
            "log_stream_name": "ai-{hostname}-{instance_id}",
            "timezone": "Local",
            "multi_line_start_pattern": "^(INFO|ERROR|WARNING|DEBUG):\\s{2,}|^[0-9]{4}-[0-9]{2}-[0-9]{2}T"
          }
        ]
      }
    }
  },
  "metrics": {
    "append_dimensions": {
      "AutoScalingGroupName": "${aws:AutoScalingGroupName}",
      "InstanceId": "${aws:InstanceId}"
    },
    "aggregation_dimensions": [
      ["AutoScalingGroupName"]
    ],
    "metrics_collected": {
      "cpu": {
        "measurement": ["cpu_usage_idle","cpu_usage_user","cpu_usage_system","cpu_usage_iowait"],
        "totalcpu": true,
        "metrics_collection_interval": 60
      },
      "mem": {
        "measurement": ["mem_used_percent","mem_available","mem_total"],
        "metrics_collection_interval": 60
      },
      "swap": {
        "measurement": ["swap_used_percent"],
        "metrics_collection_interval": 60
      },
      "disk": {
        "measurement": ["used_percent","inodes_free"],
        "resources": ["*"],
        "metrics_collection_interval": 60
      },
      "net": {
        "measurement": ["bytes_sent","bytes_recv"],
        "metrics_collection_interval": 60
      }
    }
  }
}
EOF

# 2) 적용 + 시작
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json \
  -s

# ===== 사용자 설정 (민감정보 하드코딩 금지) =====
REGION="ap-northeast-2"
ACCOUNT_ID="713881824287"
REPO_NAME="planit-ai"
IMAGE_TAG="{{IMAGE_TAG}}"   # CD에서 sha-xxxxxxx 주입

APP_DIR="/opt/planit"
LOG_DIR="/var/log/planit/ai"
ENV_FILE="${APP_DIR}/.env"

HOST="0.0.0.0"
PORT="8000"

LLM_CLIENT_TIMEOUT="3000"
LLM_CLIENT_MAX_RETRIES="3"
VLLM_CLIENT_MAX_TOKENS="16384"
LLM_CLIENT_TEMPERATURE="0.95"
LLM_CLIENT_TOP_P="0.95"

OPENAI_MODEL="gpt-4.1-nano"
VLLM_MODEL="openai/gpt-oss-20b"

# SSM Parameter prefix (필요하면 환경별로 /planit/prod/ai, /planit/dev/ai 이런 식)
SSM_PREFIX="/planit/prod/ai"
# ===== 사용자 설정 끝 =====

APP_IMAGE="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO_NAME}:${IMAGE_TAG}"

# 필수 패키지
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y jq curl awscli
elif command -v yum >/dev/null 2>&1; then
  sudo yum install -y jq curl awscli
fi

# ASG 기동 시 Docker 선기동 보장
if command -v systemctl >/dev/null 2>&1; then
  systemctl enable docker
  systemctl start docker || true
  for i in {1..60}; do
    if docker info >/dev/null 2>&1; then break; fi
    if [[ $i -eq 60 ]]; then echo "Docker not ready after 60s"; exit 1; fi
    sleep 1
  done
fi

mkdir -p "${APP_DIR}" "${LOG_DIR}"
cd "${APP_DIR}"

get_ssm() {
  local name="$1"
  aws ssm get-parameter \
    --region "${REGION}" \
    --name "${name}" \
    --with-decryption \
    --query 'Parameter.Value' \
    --output text
}

# 비밀키는 SSM에서 로드 (인스턴스 Role에 ssm:GetParameter 필요)
OPENAI_API_KEY="$(get_ssm "${SSM_PREFIX}/OPENAI_API_KEY")"
TAVILY_API_KEY="$(get_ssm "${SSM_PREFIX}/TAVILY_API_KEY")"
GOOGLE_MAPS_API_KEY="$(get_ssm "${SSM_PREFIX}/GOOGLE_MAPS_API_KEY")"
LANGEXTRACT_API_KEY="$(get_ssm "${SSM_PREFIX}/LANGEXTRACT_API_KEY")"
VLLM_BASE_URL="$(get_ssm "${SSM_PREFIX}/VLLM_BASE_URL")"

# .env 생성 (여기서만 xtrace 끄기: 로그 유출 방지)
set +x
cat > "${ENV_FILE}" <<EOF
HOST=${HOST}
PORT=${PORT}

LLM_CLIENT_TIMEOUT=${LLM_CLIENT_TIMEOUT}
LLM_CLIENT_MAX_RETRIES=${LLM_CLIENT_MAX_RETRIES}
VLLM_CLIENT_MAX_TOKENS=${VLLM_CLIENT_MAX_TOKENS}
LLM_CLIENT_TEMPERATURE=${LLM_CLIENT_TEMPERATURE}
LLM_CLIENT_TOP_P=${LLM_CLIENT_TOP_P}

OPENAI_API_KEY=${OPENAI_API_KEY}
OPENAI_MODEL=${OPENAI_MODEL}

TAVILY_API_KEY=${TAVILY_API_KEY}
GOOGLE_MAPS_API_KEY=${GOOGLE_MAPS_API_KEY}
LANGEXTRACT_API_KEY=${LANGEXTRACT_API_KEY}

VLLM_BASE_URL=${VLLM_BASE_URL}
VLLM_MODEL=${VLLM_MODEL}
EOF
chmod 600 "${ENV_FILE}"
set -x

# ECR 로그인
aws ecr get-login-password --region "${REGION}" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

# docker-compose.yml 생성
cat > docker-compose.yml <<EOF
services:
  ai:
    image: ${APP_IMAGE}
    container_name: planit-ai
    env_file:
      - ${ENV_FILE}
    ports:
      - "${PORT}:${PORT}"
    volumes:
      - ${LOG_DIR}:/var/log/planit/ai
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:${PORT}/health"]
      interval: 10s
      timeout: 3s
      retries: 10
EOF

docker compose pull
docker compose up -d