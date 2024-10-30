#Download the mde_installer.sh: https://github.com/microsoft/mdatp-xplat/blob/master/linux/installation/mde_installer.sh
install_mdatp_package:
  cmd.run:
    - name: /srv/salt/mde/mde_installer.sh --install
    - shell: /bin/bash
    - unless: 'pgrep -f mde_installer.sh'

#Download the onboarding json from your tenant and place it 
copy_mde_onboarding_file:
  file.managed:
    - name: /etc/opt/microsoft/mdatp/mdatp_onboard.json
    - source: salt://mde/mdatp_onboard.json
    - required: install_mdatp_package
