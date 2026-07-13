# Medical records models are intentionally not registered in the Django
# admin: prescriptions, diagnoses, and vitals are clinical data that must
# not be visible to admin accounts (which are superusers).
