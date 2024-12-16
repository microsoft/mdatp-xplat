# Puppet manifest to install Microsoft Defender for Endpoint on Linux.
# @param channel The release channel based on your environment, insider-fast or prod.

class install_mdatp::configure_debian_repo (
  String $channel,
  String $distro,
  String $version ) {
  # Configure the APT repository for Debian-based systems

  $release = $channel ? {
    'prod'  => $facts['os']['distro']['codename'],
    default => $channel
    }
  
  apt::source { 'microsoftpackages':
    location => "https://packages.microsoft.com/${distro}/${version}/prod",
    release  => $release,
    repos    => 'main',
    key      => {
      'id'     => 'BC528686B50D79E339D3721CEB3E94ADBE1229CF',
      'server' => 'keyserver.ubuntu.com',
    },
  }
}

class install_mdatp::configure_redhat_repo (
  String $channel,
  String $distro,
  String $version) {
  # Configure the Yum repository for RedHat-based systems
  
  yumrepo { 'microsoftpackages':
    baseurl  => "https://packages.microsoft.com/rhel/${version}/prod",
    descr    => 'packages-microsoft-com-prod',
    enabled  => 1,
    gpgcheck => 1,
    gpgkey   => 'https://packages.microsoft.com/keys/microsoft.asc',
  }
}

class install_mdatp::install {
  # Common configurations for both Debian and RedHat
  
  file { ['/etc/opt', '/etc/opt/microsoft', '/etc/opt/microsoft/mdatp']:
    ensure  => directory,
    owner   => 'root',
    group   => 'root',
    mode    => '0755',
  }

  file { '/etc/opt/microsoft/mdatp/mdatp_onboard.json':
    source  => 'puppet:///modules/install_mdatp/mdatp_onboard.json',
    owner   => 'root',
    group   => 'root',
    mode    => '0600',
    require => File['/etc/opt/microsoft/mdatp'],
  }

  # Install mdatp package
  package { 'mdatp':
    ensure  => installed,
    require => [
      File['/etc/opt/microsoft/mdatp/mdatp_onboard.json'],
    ],
  }
}


class install_mdatp (
  $channel = 'prod'
) {
  # Include the appropriate class based on the OS family
  
  $distro = downcase($facts['os']['name'])
  $version = $facts['os']['release']['major']
  
  case $facts['os']['family'] {
    'Debian': {
      class { 'install_mdatp::configure_debian_repo':
        channel => 'prod',
        distro => $distro,
        version => $version
        } -> class { 'install_mdatp::install': }
    }
    'RedHat': {
      class { 'install_mdatp::configure_redhat_repo':
        channel => 'prod',
        distro => $distro,
        version => $version,
        } -> class { 'install_mdatp::install': }
    }
    default: { fail("${facts['os']['family']} is currently not supported.")}
  }
}
