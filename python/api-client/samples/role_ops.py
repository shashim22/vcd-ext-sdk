from vcloud.rest.openapi.models.role import Role
from samples.ops_base import OpsBase

APPLICATION_JSON = 'application/json'


class RoleOps(OpsBase):
    def __init__(self):
        super().__init__()

    def create(self):
        role_model = Role(name='test_role',
                          description='Test role created by Python vCD client')
        role = self.client.post_resource(
            href=self.client.get_cloudapi_uri('/1.0.0/roles'),
            media_type=APPLICATION_JSON,
            content=role_model,
            response_type=Role)
        return role

    def update(self, href, resource):
        self.client.put_resource(href=href,
                                 media_type=APPLICATION_JSON,
                                 content=resource,
                                 response_type=Role)
        self.client.wait_for_last_task()

    def get(self, href):
        return self.client.get_resource(href=href, response_type=Role)

    def delete(self, href):
        self.client.delete_resource(href=href)
        self.client.wait_for_last_task()

    def find_first_link(self, rel, model):
        for link in self.client.get_last_links():
            if rel in link.rel.split() and model == link.model:
                return link
        return None


def main():
    role_ops = RoleOps()

    # login
    role_ops.login()

    # Create an org with basic details
    role = role_ops.create()

    # Getting edit link
    # link = role_ops.find_first_link(rel='edit', model='Role')
    link = role_ops.client.find_link(rel='edit',
                                     search_attrs={'model': 'Role'})
    assert link is not None, 'Edit link is not found!'
    # Update the description
    role.description = 'Updated description'
    role_ops.update(link.href, role)

    # Get updated org
    href = role_ops.client.get_last_header('Content-Location')
    role = role_ops.read(href)

    # Delete the org
    link = role_ops.find_first_link(rel='remove', model='Role')
    assert link is not None, 'Remove link is not found!'
    role_ops.delete(link.href)

    # logout
    role_ops.logout()


if __name__ == '__main__':
    main()
