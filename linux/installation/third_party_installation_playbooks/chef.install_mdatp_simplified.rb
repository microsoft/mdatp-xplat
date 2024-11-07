mdatp = "/etc/opt/microsoft/mdatp"

#Download the onboarding json from tenant, keep the same at specific location
onboarding_script = "/tmp/MicrosoftDefenderATPOnboardingLinuxServer.py"

#Download the installer script from: https://github.com/microsoft/mdatp-xplat/blob/master/linux/installation/mde_installer.sh
#Place the same at specific location, edit this if needed
mde_installer= "/tmp/mde_installer.sh"


## Invokve the mde-installer script 
bash 'Installing mdatp using mde-installer' do
  code <<-EOS
  chmod +x #{mde_installer}
  #{mde_installer} --install --onboard #{onboarding_script}
  EOS
end

