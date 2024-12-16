#Download the mde_installer.sh: https://github.com/microsoft/mdatp-xplat/blob/master/linux/installation/mde_installer.sh
install_mdatp_package:
  cmd.run:
    - name: /srv/salt/mde/mde_installer.sh --install --onboard /srv/salt/mde/mdatp_onboard.json
    - shell: /bin/bash
    - unless: 'pgrep -f mde_installer.sh'

