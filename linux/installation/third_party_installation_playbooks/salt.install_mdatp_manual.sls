add_ms_repo:
  pkgrepo.managed:
    - humanname: Microsoft Defender Repository
    {% if grains['os_family'] == 'Debian' %}
    - name: deb [arch=amd64,armhf,arm64] https://packages.microsoft.com/ubuntu/22.04/prod jammy main
    - dist: jammy
    - file: /etc/apt/sources.list.d/microsoft-prod.list
    - key_url: https://packages.microsoft.com/keys/microsoft.asc
    - refresh: true
    {% endif %}

install_mdatp_package:
  pkg.installed:
    - name: mdatp
    - required: add_ms_repo

copy_mde_onboarding_file:
  file.managed:
    - name: /etc/opt/microsoft/mdatp/mdatp_onboard.json
    - source: salt://mde/mdatp_onboard.json
    - required: install_mdatp_package
