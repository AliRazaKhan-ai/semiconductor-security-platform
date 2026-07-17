from .service import ComplianceService
def build_compliance_service(*,project_root,config,event_store,publisher,blockchain_service):return ComplianceService(project_root,config,event_store,publisher,blockchain_service)
