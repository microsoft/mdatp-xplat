#Add Microsoft Defender
case node['platform_family']
when 'debian'
 apt_repository 'MDATPRepo' do
   arch               'amd64'
   cache_rebuild      true
   cookbook           false
   deb_src            false
   key                'BC528686B50D79E339D3721CEB3E94ADBE1229CF'
   keyserver          "keyserver.ubuntu.com"
   distribution       'jammy'
   repo_name          'microsoft-prod'
   components         ['main']
   uri                "https://packages.microsoft.com/ubuntu/22.04/prod"
 end
apt_package "mdatp"
when 'rhel'
 yum_repository 'microsoft-prod' do
   baseurl            "https://packages.microsoft.com/rhel/7/prod/"
   description        "Microsoft Defender for Endpoint"
   enabled            true
   gpgcheck           true
   gpgkey             "https://packages.microsoft.com/keys/microsoft.asc"
 end
 if node['platform_version'] <= 8 then
    yum_package "mdatp"
 else
    dnf_package "mdatp"
 end
end

#Create MDATP Directory
mdatp = "/etc/opt/microsoft/mdatp"
onboarding_json = "/tmp/mdatp_onboard.json"

directory "#{mdatp}" do
  owner 'root'
  group 'root'
  mode 0755
  recursive true
end

#Onboarding using tenant json 
file "#{mdatp}/mdatp_onboard.json" do
  content lazy { ::File.open(onboarding_json).read }
  owner 'root'
  group 'root'
  mode '0644'
  action :create_if_missing
end
