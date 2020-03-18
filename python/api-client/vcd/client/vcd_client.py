from enum import Enum
import json
import logging
import logging.handlers as handlers
from pathlib import Path

import urllib3
from six.moves import http_client

from vcloud.api.rest.schema.versioning.supported_versions_type import (
    SupportedVersionsType)
from vcloud.api.rest.schema_v1_5.error_type import ErrorType
from vcloud.api.rest.schema_v1_5.task_type import TaskType
from vcloud.rest.openapi.models.link import Link
from vcloud.rest.openapi.models.session import Session
from vcloud.rest.openapi.models.sessions import Sessions
from .api_client import ApiClient
from .exceptions import (
    AccessForbiddenException, BadRequestException, ClientException,
    ConflictException, InternalServerException, InvalidContentLengthException,
    MethodNotAllowedException, NotAcceptableException, NotFoundException,
    RequestTimeoutException, UnauthorizedException, UnknownApiException,
    UnsupportedMediaTypeException)
from .rest import ApiException
from .task_monitor import TaskMonitor


class BasicLoginCredentials(object):
    def __init__(self, user, org, password):
        self.user = user
        self.org = org
        self.password = password


class BearerLoginCredentials(object):
    def __init__(self, bearer_token):
        self.bearer_token = bearer_token


class VcdClient(ApiClient):
    """A client to interact with the vCloud Director OpenAPI.

    Client defaults to the highest API version supported by vCloud Director
    when api_Version is not provided. You can also set the version explicitly
    using the api_version parameter.

    :param str uri: vCD server host name or connection URI.
    :param str api_version: vCD API version to use.
    :param boolean verify_ssl_certs: If True validate server certificate;
        False allows self-signed certificates.
    :param str log_file: log file name or None, which suppresses logging.
    """
    _API = '/api'
    _CLOUDAPI = '/cloudapi'

    APPLICATION_JSON = 'application/json'
    APPLICATION_JSON_VCLOUD = 'application/*+json'

    _HEADER_ACCEPT = 'Accept'
    _HEADER_AUTHORIZATION = 'Authorization'
    _HEADER_CONTENT_TYPE = 'Content-Type'
    _HEADER_LINK = 'Link'
    _HEADER_LOCATION = 'Location'
    _HEADER_X_VCLOUD_TOKEN_TYPE = 'X-VMWARE-VCLOUD-TOKEN-TYPE'
    _HEADER_X_VCLOUD_ACCESS_TOKEN = 'X-VMWARE-VCLOUD-ACCESS-TOKEN'
    _HEADER_X_VCLOUD_REQUEST_ID = 'X-VMWARE-VCLOUD-REQUEST-ID'

    _BEARER_TOKEN_TYPE = 'Bearer'

    _HEADERS_TO_REDACT = [
        'Authorization', 'x-vcloud-authorization',
        'X-VMWARE-VCLOUD-ACCESS-TOKEN'
    ]

    DEFAULT_LOG_FILE = 'vcd_client.log'

    def __init__(self,
                 host,
                 api_version=None,
                 verify_ssl=True,
                 log_file=None,
                 log_bodies=False,
                 log_headers=False):
        self._base_uri = host
        self._prepare_base_uri()

        self._api_version = api_version

        self._logger = None
        self._urllib3_logger = None
        self._set_loggers(file_name=log_file)

        # Disable HTTP debug logging on stdout
        http_client.HTTPConnection.debuglevel = 0

        self._status = None
        self._headers = None
        self._task = None
        self._links = None
        self._task_monitor = None

        # Session of logged in user
        self._session = None

        # Initialize ApiClient
        super().__init__(logger=self._logger,
                         log_bodies=log_bodies,
                         log_headers=log_headers,
                         verify_ssl=verify_ssl)

    def _prepare_base_uri(self):
        if len(self._base_uri) > 0:
            if self._base_uri[-1] == '/':
                self._base_uri = self._base_uri[0:len(self._base_uri) - 1]
            if not self._base_uri.startswith(
                    'https://') and not self._base_uri.startswith('http://'):
                self._base_uri = 'https://' + self._base_uri

    def get_rest_uri(self, resource_path):
        return self._base_uri + self._API + resource_path

    def get_cloudapi_uri(self, resource_path):
        return self._base_uri + self._CLOUDAPI + resource_path

    def _set_loggers(self,
                     file_name,
                     log_level=logging.DEBUG,
                     max_bytes=30000000,
                     backup_count=30):
        """This will set the default logger with Rotating FileHandler.

        Open the specified file and use it as the stream for logging.
        By default, the file grows indefinitely. You can specify particular
        values of maxBytes and backupCount to allow the file to rollover at
        a predetermined size.
        Rollover occurs whenever the current log file is nearly maxBytes in
        length. If backupCount is >= 1, the system will successively create
        new files with the same pathname as the base file, but with extensions
        ".1", ".2" etc. appended to it. For example, with a backupCount of 5
        and a base file name of "app.log", you would get "app.log",
        "app.log.1", "app.log.2", ... through to "app.log.5". The file being
        written to is always "app.log" - when it gets filled up, it is closed
        and renamed to "app.log.1", and if files "app.log.1", "app.log.2" etc.
        exist, then they are renamed to "app.log.2", "app.log.3" etc.
        respectively.

        :param file_name: name of the log file.
        :param log_level: log level.
        :param max_bytes: max size of log file in bytes.
        :param backup_count: no of backup count.
        """
        self._logger = logging.getLogger(__name__)
        self._logger.setLevel(log_level)
        self._urllib3_logger = logging.getLogger('urllib3')
        self._urllib3_logger.setLevel(log_level)

        if file_name is None:
            file_name = self.DEFAULT_LOG_FILE
        file = Path(file_name)
        if not file.exists():
            file.parent.mkdir(parents=True, exist_ok=True)

        if not self._logger.handlers:
            default_log_handler = handlers.RotatingFileHandler(
                filename=file_name,
                maxBytes=max_bytes,
                backupCount=backup_count)
            default_log_handler.setLevel(log_level)
            self._logger.addHandler(default_log_handler)
            self._urllib3_logger.addHandler(default_log_handler)

    def set_credentials(self, creds):
        """Set credentials and authenticate to create a new session.

        This call will automatically set the highest supported API version if
        it was not set previously.

        :param BasicLoginCredentials creds: Credentials containing org,
            user, and password.

        :raises: VcdException: if automatic API negotiation fails to arrive
        """
        if self._api_version is None:
            self.set_highest_supported_version()

        if isinstance(creds, BasicLoginCredentials):
            self._login(self._is_provider(creds.org), creds)
        elif isinstance(creds, BearerLoginCredentials):
            self._validate_session(creds)

        self._logger.debug('User %s logged in to %s org.' %
                           (self.get_user(), self.get_org()))

    def set_auth_header(self, auth_token):
        self.set_default_header(self._HEADER_AUTHORIZATION, auth_token)

    def set_highest_supported_version(self):
        """Set the client API version to the highest server API version.

        This call is intended to make it easy to work with new vCD features
        before they are officially supported in pylib. Applications should
        set the API version explicitly to freeze compatibility.

        :return: selected api version.

        :rtype: str
        """
        active_versions = set([
            version_info.version
            for version_info in self.get_supported_versions().version_info
        ])
        active_versions = list(active_versions)
        active_versions.sort()
        self._api_version = active_versions[-1]
        self._logger.debug('API versions supported: %s' % active_versions)
        self._logger.debug('API version set to %s' % self._api_version)
        return self._api_version

    @staticmethod
    def _is_provider(org):
        if org.lower() == 'system':
            return True
        return False

    def _login(self, is_provider, creds):
        if is_provider:
            login_url = self.get_cloudapi_uri('/1.0.0/sessions/provider')
        else:
            login_url = self.get_cloudapi_uri('/1.0.0/sessions')

        basic_auth_token = urllib3.util.make_headers(
            basic_auth='%s@%s:%s' %
            (creds.user, creds.org, creds.password)).get('authorization')
        header_params = {self._HEADER_AUTHORIZATION: basic_auth_token}
        self._session = self.post_resource(login_url,
                                           header_params=header_params,
                                           response_type=Session)
        # Store authentication token
        self._store_session_token(
            self._headers.get(self._HEADER_X_VCLOUD_TOKEN_TYPE),
            self._headers.get(self._HEADER_X_VCLOUD_ACCESS_TOKEN))

    def _validate_session(self, creds):
        login_url = self.get_cloudapi_uri('/1.0.0/sessions')
        header_params = {
            self._HEADER_AUTHORIZATION: 'Bearer %s' % creds.bearer_token
        }
        sessions = self.get_resource(login_url,
                                     header_params=header_params,
                                     response_type=Sessions)
        if len(sessions.values) > 0:
            self._session = sessions.values[0]
            self._store_session_token(self._BEARER_TOKEN_TYPE,
                                      creds.bearer_token)
        else:
            self._logger.error("Invalid bearer token.")

    def _store_session_token(self, token_type, access_token):
        self.set_default_header(self._HEADER_AUTHORIZATION,
                                '%s %s' % (token_type, access_token))

    def _remove_session_token(self):
        self.clear_default_header(self._HEADER_AUTHORIZATION)

    def logout(self):
        """Logout current user and clear the session.
        """
        logout_url = self.get_cloudapi_uri('/1.0.0/sessions/%s' %
                                           self._session.id)
        self.delete_resource(logout_url)
        self._remove_session_token()
        self._logger.debug('User %s logged out from %s org.' %
                           (self.get_user(), self.get_org()))
        self._session = None

    def get_org(self):
        """Returns the logged in org name.

        :return: Name of the logged in organization.

        :rtype: str
        """
        return self._session.org.name

    def get_user(self):
        """Returns the logged in user name.

        :return: Name of the logged in org.

        :rtype: str
        """
        return self._session.user.name

    def get_last_status(self):
        """Returns the status of last API call

        :return: Status code of last response

        :rtype: int
        """
        return self._status

    def get_last_links(self):
        """Returns links received in last API call

        :return: list of Links

        :rtype: list
        """
        return self._links

    def find_link(self, rel, search_attrs):
        """Finds links by relation and other attributes.

        :param str rel: Relation of the desired link.

        :param dict search_attrs: Key-value pair to filter the desired link.

        :return: First link with the given relation and search attributes,
            None otherwise.

        :rtype: list
        """
        for link in self._links:
            if rel in link.rel.split():
                link_found = True
                for attr in search_attrs:
                    if search_attrs.get(attr) != getattr(link, attr):
                        link_found = False
                        break
                if link_found:
                    return link
        return None

    def get_last_headers(self):
        """Returns response headers of last API call

        :return: response headers

        :rtype: dict
        """
        return self._headers

    def get_last_header(self, name):
        """Returns a specific response header of last API call

        :return: header value

        :rtype: str
        """
        return self._headers.get(name)

    def get_supported_versions(self):
        """Returns the list of supported API versions by vCloud director

        :return: versions as strings, sorted in ascending order

        :rtype: list
        """
        return self.get_resource(self.get_rest_uri('/versions'),
                                 response_type=SupportedVersionsType)

    def get_highest_supported_version(self):
        """Returns the highest API version supported by vCloud Director

        :return: version as string

        :rtype: str
        """
        return self.get_supported_versions()[-1]

    def get_last_task(self):
        """Returns the task of last API call

        :return: task in JSON format

        :rtype: dict
        """
        return self._task

    def get_task_monitor(self):
        if self._task_monitor is None:
            self._task_monitor = TaskMonitor(self, self._logger)
        return self._task_monitor

    def wait_for_last_task(self):
        if self._task is not None:
            return self.get_task_monitor().wait_for_success(
                self.get_last_task())

    def get_resource(self, href, response_type, header_params=None):
        """Gets an entity by href

        :return: resource in JSON format

        :rtype: dict
        """
        return self._do_request(resource_path=href,
                                method='GET',
                                response_type=response_type,
                                header_params=header_params)

    def post_resource(self,
                      href,
                      response_type,
                      media_type=None,
                      content=None,
                      header_params=None):
        if media_type:
            header_params = {self._HEADER_CONTENT_TYPE: media_type}
        return self._do_request(resource_path=href,
                                method='POST',
                                response_type=response_type,
                                body=content,
                                header_params=header_params)

    def put_resource(self,
                     href,
                     response_type,
                     media_type=None,
                     content=None,
                     header_params=None):
        if media_type:
            header_params = {self._HEADER_CONTENT_TYPE: media_type}
        return self._do_request(resource_path=href,
                                method='PUT',
                                response_type=response_type,
                                body=content,
                                header_params=header_params)

    def delete_resource(self, href, response_type=None, header_params=None):
        return self._do_request(resource_path=href,
                                method='DELETE',
                                response_type=response_type,
                                header_params=header_params)

    def execute_query(self, href, query_params, response_type):
        return self._do_request(resource_path=href,
                                method='GET',
                                query_params=query_params,
                                response_type=response_type)

    def _do_request(self,
                    resource_path,
                    method,
                    query_params=None,
                    header_params=None,
                    body=None,
                    files=None,
                    response_type=None):
        try:
            is_api_uri = self._is_api_uri(resource_path)
            if header_params is None:
                header_params = {}
            self._set_accept_header(is_api_uri, header_params)
            self._status = self._headers = self._links = self._task = None
            response_data, self._status, self._headers = super()._do_request(
                resource_path=resource_path,
                method=method,
                query_params=query_params,
                header_params=header_params,
                body=body,
                files=files,
                response_type=response_type)
            self._store_links(is_api_uri, response_data)
            self._store_task(is_api_uri, response_data)
        except ApiException as ae:
            self._status = ae.status
            error = self._ApiClient__deserialize(data=json.loads(ae.body),
                                                 klass=ErrorType)
            ex = self._get_specific_exception(
                self._status, ae.headers.get(self._HEADER_X_VCLOUD_REQUEST_ID),
                error)
            raise ex from None
        return response_data

    def _is_api_uri(self, url):
        if self._API in url:
            return True
        elif self._CLOUDAPI in url:
            return False
        else:
            raise ClientException(
                'Invalid URL, valid URL patterns are %s/api/ and %s/cloudapi/'
                % self._base_uri)

    def _set_accept_header(self, is_api_uri, header_params):

        if is_api_uri:
            accept_value = self.APPLICATION_JSON_VCLOUD
        else:
            accept_value = self.APPLICATION_JSON
        if self._api_version is not None:
            accept_value = '%s;version=%s' % (accept_value, self._api_version)
        header_params[self._HEADER_ACCEPT] = accept_value
        return header_params

    @staticmethod
    def _get_specific_exception(status, request_id, vcd_error):
        if status == 400:
            return BadRequestException(status, request_id, vcd_error)

        if status == 401:
            return UnauthorizedException(status, request_id, vcd_error)

        if status == 403:
            return AccessForbiddenException(status, request_id, vcd_error)

        if status == 404:
            return NotFoundException(status, request_id, vcd_error)

        if status == 405:
            return MethodNotAllowedException(status, request_id, vcd_error)

        if status == 406:
            return NotAcceptableException(status, request_id, vcd_error)

        if status == 408:
            return RequestTimeoutException(status, request_id, vcd_error)

        if status == 409:
            return ConflictException(status, request_id, vcd_error)

        if status == 415:
            return UnsupportedMediaTypeException(status, request_id, vcd_error)

        if status == 416:
            return InvalidContentLengthException(status, request_id, vcd_error)

        if status == 500:
            return InternalServerException(status, request_id, vcd_error)

        return UnknownApiException(status, request_id, vcd_error)

    def _store_links(self, is_api_uri, response):
        self._links = []
        if is_api_uri:
            if hasattr(response, 'link') and response.link is not None:
                self._links = response.link
        else:
            for link in self._headers.getlist(self._HEADER_LINK):
                link_entries = link.split(';')
                link = Link()
                setattr(link, 'href', link_entries[0].strip('<>'))
                for i in range(1, len(link_entries)):
                    key_value = link_entries[i].split('=')
                    setattr(link, key_value[0], key_value[1].strip('"'))
                self._links.append(link)

    def _store_task(self, is_api_uri, response):
        self._task = None
        if isinstance(response, TaskType):
            self._task = response
        if is_api_uri:
            if hasattr(response, 'tasks'):
                tasks = response.tasks
                if tasks is not None and len(tasks) > 0:
                    self._task = tasks[0]
        else:
            task_href = self._headers.get(self._HEADER_LOCATION)
            if task_href is not None:
                self._task = self.get_resource(href=task_href,
                                               response_type=TaskType)
