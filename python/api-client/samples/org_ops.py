from vcloud.api.rest.schema_v1_5.admin_org_type import AdminOrgType
from vcloud.api.rest.schema_v1_5.task_type import TaskType
from vcloud.api.rest.schema_v1_5.query_result_records_type import \
    QueryResultRecordsType
from samples.ops_base import OpsBase

ADMIN_ORG_MEDIA_TYPE = 'application/vnd.vmware.admin.organization+json'


class OrgOps(OpsBase):
    def __init__(self):
        super().__init__()

    def create(self):
        org_model = AdminOrgType()
        org_model.name = 'test_org'
        org_model.full_name = 'test_org'
        org_model.is_enabled = True
        org_model.description = 'Test org created by Python vCD client'
        org_model.settings = {}

        org = self.client.post_resource(
            href=self.client.get_rest_uri('/admin/orgs'),
            media_type=ADMIN_ORG_MEDIA_TYPE,
            content=org_model,
            response_type=AdminOrgType,
        )
        return org

    def read(self, href):
        return self.client.get_resource(href=href, response_type=AdminOrgType)

    def update(self, href, resource):
        self.client.put_resource(href=href,
                                 media_type=ADMIN_ORG_MEDIA_TYPE,
                                 content=resource,
                                 response_type=AdminOrgType)
        self.client.wait_for_last_task()

    def delete(self, href):
        self.client.delete_resource(href=href, response_type=TaskType)
        self.client.wait_for_last_task()

    def query(self, href=None):
        query_params = {'type': 'organization', 'format': 'records'}
        return self.client.execute_query(
            href=self.client.get_rest_uri('/query'),
            query_params=query_params,
            response_type=QueryResultRecordsType)


def main():
    org_ops = OrgOps()

    # login
    org_ops.login()

    # Create an org with basic details
    org = org_ops.create()

    # Getting edit link
    link = org_ops.client.find_link(
        rel='edit', search_attrs={'type': ADMIN_ORG_MEDIA_TYPE})
    assert link is not None, 'Edit link is not found!'

    # Disable org
    org.is_enabled = False
    org_ops.update(link.href, org)

    # Get updated org
    org = org_ops.read(org.href)

    # Delete the org
    org_ops.delete(org.href)

    # Execute a simple query to get all organizations
    result = org_ops.query()
    assert result is not None, 'Empty query result'

    # logout
    org_ops.logout()


if __name__ == '__main__':
    main()