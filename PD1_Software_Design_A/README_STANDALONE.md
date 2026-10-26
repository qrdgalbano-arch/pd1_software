# PD1 Design A

Fixed renderer: component; design_scope: component.

Original PD_SOFTWARE was not changed.
Local databases/logs start separately; patient/session databases were not copied.
The original Python environment is reused; this is not yet a portable packaged executable.

Ankle endpoints: +20 degrees dorsiflexion, -50 degrees plantarflexion. These are user-requested demo settings, not PT approval. Legacy ankle counting remains scalar/plantarflexion-based.
Removed prone prescriptions must be replaced through the normal prescription workflow, not silently relabeled.

Run the included Run_Design_A.ps1 launcher.
All launchers use port 18080; run one at a time.
Do not publish .env credentials or patient data.
