# Quick Start: E2E Testing Suite

## Installation & Setup (5 minutes)

### 1. Verify Prerequisites
```bash
# Check KVM/libvirt is available
virsh list --all

# Verify Vagrant is installed with libvirt
vagrant plugin list | grep libvirt

# Python 3.8+ and PyYAML
python3 --version
pip3 install pyyaml
```

### 2. Configure Secrets
```bash
cd tests/e2e

# Copy your MDE JSON files
cp /path/to/your/onboarding.json mdatp_onboard.json
cp /path/to/your/managed_config.json mdatp_managed.json
cp /path/to/your/offboarding.json mdatp_offboard.json  # Optional

# Verify files exist and are valid JSON
python3 -c "import json; json.load(open('mdatp_onboard.json'))"
```

### 3. Review Configuration (Optional)
```bash
# View default settings
cat config.yaml

# Adjust if needed:
# - CPU budget: vagrant.cpus_total
# - Memory budget: vagrant.memory_total_mb
# - Concurrent VMs: vagrant.concurrent_vms
# - Health check timeouts: test.max_health_check_attempts
```

## Running Tests

### Test Single Distro (Best for First Run)
```bash
python3 runner.py --distro ubuntu:22.04
```
Expected: Takes ~3-5 minutes, installs on single VM

### Test All Ubuntu Versions
```bash
python3 runner.py --distro ubuntu
```

### Test Entire Debian Family
```bash
python3 runner.py --family debian
```

### Test All Discovered Distros
```bash
python3 runner.py --all
```
Expected: 30+ distros, runs in parallel, takes 30-45 minutes depending on CPU/memory

### Test Specific Subset
```bash
python3 runner.py --distros ubuntu:22.04,rocky:9,debian:12
```

### Dry Run (See What Would Execute)
```bash
python3 runner.py --all --dry-run
```

### Custom Resource Budget
```bash
# For 4-core, 8GB RAM systems
python3 runner.py --all --cpus 4 --memory 8192
```

## Understanding Results

### Summary Report
```bash
cat results/summary.md
```

Shows:
- Each distro/version tested
- Installation success (✅/❌)
- Onboarding success (✅/❌)
- Uninstall/offboarding (✅/❌)
- Test duration
- Overall status

### Detailed Results
```bash
# JSON format for programmatic parsing
cat results/results.json
```

### Failure Logs
```bash
# Individual logs for each failure
ls results/failures/
cat results/failures/rocky-9-*.log
```

## Troubleshooting

### Vagrant/KVM Issues
```bash
# Verify libvirt is running
sudo systemctl status libvirtd

# Check for stale VMs
vagrant global-status --prune
virsh list --all

# Check Vagrant logs
export VAGRANT_LOG=debug
python3 runner.py --distro ubuntu:22.04
```

### Health Check Failures
```bash
# Increase timeout in config.yaml
max_health_check_attempts: 60  # was 30

# Keep failed VM for debugging
# In config.yaml: preserve_on_failure: true
# Then SSH in to inspect
vagrant ssh
mdatp health --output json
sudo tail -f /var/log/mdatp_installer.log
```

### Secret Loading Issues
```bash
# Verify JSON files exist
ls -la mdatp_*.json

# Check they are valid JSON
python3 -c "import json; json.load(open('mdatp_onboard.json'))"
python3 -c "import json; json.load(open('mdatp_managed.json'))"

# Check files are in gitignore
grep "mdatp_" ../../.gitignore
```

## Performance Tips

- **Fastest**: Sequential testing (1 VM at a time)
  - `python3 runner.py --distro ubuntu:22.04`
  
- **Balanced**: 2-4 concurrent VMs (8 CPU, 16GB RAM system)
  - `config.yaml: concurrent_vms: 4`
  
- **Full Parallel**: 4+ concurrent VMs (16 CPU, 32GB+ RAM system)
  - `config.yaml: concurrent_vms: 8`

## Expected Runtimes

- Single distro: 2.5-3 minutes
- Full matrix (30+ distros) sequential: 1.5-2 hours
- Full matrix parallel (4 VMs): 30-45 minutes

## Common Commands Reference

```bash
# Run all Ubuntu versions
python3 runner.py --distro ubuntu

# Run RHEL family only
python3 runner.py --family fedora

# Test exact subset
python3 runner.py --distros ubuntu:20.04,ubuntu:22.04,rocky:9

# Preserve failed VMs for debugging
python3 runner.py --distro rocky:9 \
  && sed -i 's/preserve_on_failure: false/preserve_on_failure: true/' config.yaml \
  && vagrant ssh

# Dry run with verbose output
python3 runner.py --all --dry-run

# Run with 2 CPUs for slower systems
python3 runner.py --all --cpus 2 --memory 4096
```

## File Locations

- **Test runner**: `tests/e2e/runner.py`
- **Configuration**: `tests/e2e/config.yaml`
- **Secrets**: `tests/e2e/mdatp_*.json` (git-ignored)
- **Results**: `tests/e2e/results/summary.md`
- **Failure logs**: `tests/e2e/results/failures/`
- **VM definitions**: `tests/e2e/vagrant/Vagrantfile`
- **Provisioning**: `tests/e2e/vagrant/templates/*.sh`
- **Image builder**: `tests/e2e/scripts/convert_cloud_image.sh`
- **Documentation**: `tests/e2e/README.md`

## Next Steps

1. ✅ Install dependencies: `pip3 install pyyaml`
2. ✅ Configure secrets: Copy your `mdatp_onboard.json` and `mdatp_managed.json` files
3. ✅ Dry run: `python3 runner.py --all --dry-run`
4. ✅ Test single distro: `python3 runner.py --distro ubuntu:22.04`
5. ✅ Run full suite: `python3 runner.py --all`
6. ✅ Review results: `cat results/summary.md`

---

**More Info**: See `tests/e2e/README.md` for comprehensive documentation  
**Architecture**: See `tests/e2e/IMPLEMENTATION_SUMMARY.md` for technical details
