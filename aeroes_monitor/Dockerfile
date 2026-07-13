# Imagem Lambda do aeroes_monitor: Python 3.13 + Chrome for Testing pinado.
# Chrome e chromedriver vêm JUNTOS e na MESMA versão (ARG abaixo): o
# Selenium Manager acha ambos locais e não baixa nada em runtime.
# Para atualizar o pin:
#   curl -s https://googlechromelabs.github.io/chrome-for-testing/LATEST_RELEASE_STABLE
FROM public.ecr.aws/lambda/python:3.13

ARG CHROME_VERSION=150.0.7871.115
ARG CFT_BASE=https://storage.googleapis.com/chrome-for-testing-public

# Bibliotecas de sistema do Chrome headless em AL2023 (lista validada pela
# comunidade para imagens Lambda; enxugar depois, se quiser, medindo).
RUN dnf install -y unzip \
      atk at-spi2-atk cups-libs gtk3 pango alsa-lib nss mesa-libgbm \
      libXcomposite libXcursor libXdamage libXext libXi libXrandr \
      libXScrnSaver libXtst libXt libxkbcommon libdrm \
      dbus-glib xorg-x11-server-Xvfb \
    && dnf clean all

RUN curl -sSLo /tmp/chrome.zip "${CFT_BASE}/${CHROME_VERSION}/linux64/chrome-linux64.zip" \
    && curl -sSLo /tmp/chromedriver.zip "${CFT_BASE}/${CHROME_VERSION}/linux64/chromedriver-linux64.zip" \
    && unzip -q /tmp/chrome.zip -d /opt \
    && unzip -q /tmp/chromedriver.zip -d /opt \
    && ln -s /opt/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver \
    && rm -f /tmp/chrome.zip /tmp/chromedriver.zip

# TZ é chave RESERVADA nas env vars da função (CloudFormation rejeita);
# na imagem tem o mesmo efeito: timestamps de log/debug em BRT.
ENV TZ=America/Sao_Paulo

COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY availability.py browser.py config.py discord.py handler.py login.py \
     main.py models.py notifications.py report.py saga_data.py scheduler.py \
     utils.py config.lambda.ini ${LAMBDA_TASK_ROOT}/

CMD ["handler.lambda_handler"]
