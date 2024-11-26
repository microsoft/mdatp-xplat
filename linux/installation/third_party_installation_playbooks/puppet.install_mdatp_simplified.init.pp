# Puppet manifest to install Microsoft Defender for Endpoint on Linux.
# @param channel The release channel based on your environment, insider-fast or prod.

class install_mdatp (
  $channel = 'prod',
) {
  # Ensure that the directory /tmp/mde_install exists
  file { '/tmp/mde_install':
    ensure => directory,
    mode   => '0755',
  }

  # Copy the installation script to the destination
  file { '/tmp/mde_install/mde_installer.sh':
    ensure => file,
    source => 'puppet:///modules/install_mdatp/mde_installer.sh',
    mode   => '0777',
  }

  # Copy the onboarding script to the destination
  file { '/tmp/mde_install/mdatp_onboard.json':
    ensure => file,
    source => 'puppet:///modules/install_mdatp/mdatp_onboard.json',
    mode   => '0777',
  }

  #Install MDE on the host using an external script
  exec { 'install_mde':
    command     => "/tmp/mde_install/mde_installer.sh --install --channel ${channel} --onboard /tmp/mde_install/mdatp_onboard.json",
    path        => '/bin:/usr/bin',
    user        => 'root',
    logoutput   => true,
    require     => File['/tmp/mde_install/mde_installer.sh', '/tmp/mde_install/mdatp_onboard.json'], # Ensure the script is copied before running the installer
  }

}
