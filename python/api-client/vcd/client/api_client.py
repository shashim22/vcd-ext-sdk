from __future__ import absolute_import

import os
import re
import json
import mimetypes
import tempfile
from dateutil.parser import parse
from datetime import date, datetime

from six import integer_types, iteritems, text_type

import inspect
from importlib import import_module

from vcloud.rest.openapi import models
from vcloud.api.rest import schema_v1_5
from vcloud.api.rest.schema_v1_5 import extension
from vcloud.api.rest.schema_v1_5.query_result_record_type import  QueryResultRecordType
from vcloud.api.rest.schema import ovf, versioning
from vcloud.api.rest.schema.ovf import environment, vmware
from vcloud.rest.openapi.models import session
from vcd.client.rest import ApiException, RESTClientObject
from enum import Enum


class ApiClient(object):

    PRIMITIVE_TYPES = (float, bool, bytes, text_type) + integer_types
    NATIVE_TYPES_MAPPING = {
        'int': int,
        'long': int,
        'float': float,
        'str': str,
        'bool': bool,
        'date': date,
        'datetime': datetime,
        'object': object,
    }

    REQUEST = 'Request'
    RESPONSE = 'Response'

    def __init__(self,
                 logger,
                 log_bodies=False,
                 log_headers=False,
                 verify_ssl=True):
        """
        Constructor of the class.
        """
        self._logger = logger
        self._log_bodies = log_bodies
        self._log_headers = log_headers

        self.rest_client = RESTClientObject(verify_ssl=verify_ssl)

        self._default_headers = {}

        self.safe_chars_for_path_param = ':'
        self.temp_folder_path = ''
        # Set default User-Agent.
        self.user_agent = 'vcd-client/python'

        # Load all cloudapi model classes in models
        for file in os.listdir(os.path.dirname(session.__file__)):
            mod_name = file[:-3]
            if mod_name.startswith('__'):
                continue
            module = import_module('vcloud.rest.openapi.models.' + mod_name)
            setattr(models, mod_name, module)
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if inspect.isclass(obj):
                    setattr(models, name, obj)

    def set_default_header(self, header_name, header_value):
        self._default_headers[header_name] = header_value

    def clear_default_header(self, header_name):
        del self._default_headers[header_name]

    def sanitize_for_serialization(self, obj):
        """
        Builds a JSON POST object.

        If obj is None, return None.
        If obj is str, int, long, float, bool, return directly.
        If obj is datetime.datetime, datetime.date
            convert to string in iso8601 format.
        If obj is list, sanitize each element in the list.
        If obj is dict, return the dict.
        If obj is swagger model, return the properties dict.

        :param obj: The data to serialize.
        :return: The serialized form of data.
        """
        if obj is None:
            return None
        elif isinstance(obj, self.PRIMITIVE_TYPES):
            return obj
        elif isinstance(obj, list):
            return [
                self.sanitize_for_serialization(sub_obj) for sub_obj in obj
            ]
        elif isinstance(obj, tuple):
            return tuple(
                self.sanitize_for_serialization(sub_obj) for sub_obj in obj)
        elif isinstance(obj, (datetime, date)):
            return obj.isoformat()

        if isinstance(obj, dict):
            obj_dict = obj
        else:
            # Convert model obj to dict except
            # attributes `swagger_types`, `attribute_map`
            # and attributes which value is not None.
            # Convert attribute name to json key in
            # model definition for request.
            if isinstance(obj, Enum):
                return obj.value

            obj_dict = {}
            cls_tree = list(inspect.getmro(obj.__class__))
            cls_tree.remove(object)
            for cls in cls_tree:
                current_dict = {
                    cls.attribute_map[attr]: getattr(obj, attr)
                    for attr, _ in iteritems(cls.swagger_types)
                    if hasattr(obj, attr) and getattr(obj, attr) is not None
                }
                obj_dict.update(current_dict)

        return {
            key: self.sanitize_for_serialization(val)
            for key, val in iteritems(obj_dict)
        }

    def deserialize(self, response, response_type):
        """
        Deserializes response into an object.

        :param response: RESTResponse object to be deserialized.
        :param response_type: class literal for
            deserialized object, or string of class name.

        :return: deserialized object.
        """
        # handle file downloading
        # save response body into a tmp file and return the instance
        if response_type == "file":
            return self.__deserialize_file(response)

        # fetch data from response object
        try:
            data = json.loads(response.data)
        except ValueError:
            data = response.data

        return self.__deserialize(data, response_type)

    def __deserialize(self, data, klass):
        """
        Deserializes dict, list, str into an object.

        :param data: dict, list or str.
        :param klass: class literal, or string of class name.

        :return: object.
        """
        if data is None:
            return None

        if type(klass) == str:
            if klass.startswith('list['):
                sub_kls = re.match('list\[(.*)\]', klass).group(1)
                return [
                    self.__deserialize(sub_data, sub_kls) for sub_data in data
                ]

            if klass.startswith('dict('):
                sub_kls = re.match('dict\(([^,]*), (.*)\)', klass).group(2)
                return {
                    k: self.__deserialize(v, sub_kls)
                    for k, v in iteritems(data)
                }

            # convert str to class
            if klass in self.NATIVE_TYPES_MAPPING:
                klass = self.NATIVE_TYPES_MAPPING[klass]
            else:
                if hasattr(models, klass):
                    klass = getattr(models, klass)
                elif hasattr(schema_v1_5, klass):
                    klass = getattr(schema_v1_5, klass)
                elif hasattr(extension, klass):
                    klass = getattr(extension, klass)
                elif hasattr(ovf, klass):
                    klass = getattr(ovf, klass)
                elif hasattr(versioning, klass):
                    klass = getattr(versioning, klass)
                elif hasattr(environment, klass):
                    klass = getattr(environment, klass)
                elif hasattr(vmware, klass):
                    klass = getattr(vmware, klass)

        if klass in self.PRIMITIVE_TYPES:
            return self.__deserialize_primitive(data, klass)
        elif klass == object:
            return self.__deserialize_object(data)
        elif klass == date:
            return self.__deserialize_date(data)
        elif klass == datetime:
            return self.__deserialize_datatime(data)
        else:
            return self.__deserialize_model(data, klass)

    def _do_request(self,
                    resource_path,
                    method,
                    query_params=None,
                    header_params=None,
                    body=None,
                    post_params=None,
                    files=None,
                    response_type=None):
        """
        Makes the HTTP request (synchronous) and return the deserialized data.
        To make an async request, define a function for callback.

        :param resource_path: Path to method endpoint.
        :param method: Method to call.
        :param query_params: Query parameters in the url.
        :param header_params: Header parameters to be
            placed in the request header.
        :param body: Request body.
        :param post_params dict: Request post form parameters,
            for `application/x-www-form-urlencoded`, `multipart/form-data`.
        :param files dict: key -> filename, value -> filepath,
            for `multipart/form-data`.
        :param response_type: Response data type.
        :return:
            The method will return the response directly.
        """
        # header parameters
        header_params = header_params or {}
        header_params.update(self._default_headers)
        if header_params:
            header_params = self.sanitize_for_serialization(header_params)
            header_params = dict(self.parameters_to_tuples(header_params))

        # query parameters
        if query_params:
            query_params = self.sanitize_for_serialization(query_params)
            query_params = self.parameters_to_tuples(query_params)

        # post parameters
        if post_params or files:
            post_params = self.prepare_post_parameters(post_params, files)
            post_params = self.sanitize_for_serialization(post_params)
            post_params = self.parameters_to_tuples(post_params)

        # body
        if body:
            body = self.sanitize_for_serialization(body)

        # request url
        url = resource_path

        # log request headers and body
        if self._log_headers:
            self._do_log_headers(headers=header_params, type=self.REQUEST)
        if self._log_bodies:
            self._do_log_bodies(body=json.dumps(body), type=self.REQUEST)

        # perform request and return response
        response_data = self.rest_client.request(method,
                                                 url,
                                                 query_params=query_params,
                                                 headers=header_params,
                                                 post_params=post_params,
                                                 body=body)

        # log response headers and body
        if self._log_headers:
            self._do_log_headers(headers=response_data.getheaders(),
                                 type=self.RESPONSE)
        if self._log_bodies:
            self._do_log_bodies(body=response_data.data, type=self.RESPONSE)

        if response_type:
            return_data = self.deserialize(response_data, response_type)
        else:
            return_data = None

        return (return_data, response_data.status, response_data.getheaders())

    def parameters_to_tuples(self, params):
        """
        Get parameters as list of tuples, formatting collections.

        :param params: Parameters as dict or list of two-tuples
        :return: Parameters as list of tuples, collections formatted
        """
        new_params = []
        for k, v in iteritems(params) if isinstance(params, dict) else params:
            new_params.append((k, v))
        return new_params

    def prepare_post_parameters(self, post_params=None, files=None):
        """
        Builds form parameters.

        :param post_params: Normal form parameters.
        :param files: File parameters.
        :return: Form parameters with files.
        """
        params = []

        if post_params:
            params = post_params

        if files:
            for k, v in iteritems(files):
                if not v:
                    continue
                file_names = v if type(v) is list else [v]
                for n in file_names:
                    with open(n, 'rb') as f:
                        filename = os.path.basename(f.name)
                        filedata = f.read()
                        mimetype = mimetypes.guess_type(
                            filename)[0] or 'application/octet-stream'
                        params.append(
                            tuple([k, tuple([filename, filedata, mimetype])]))

        return params

    def select_header_accept(self, accepts):
        """
        Returns `Accept` based on an array of accepts provided.

        :param accepts: List of headers.
        :return: Accept (e.g. application/json).
        """
        if not accepts:
            return

        accepts = [x.lower() for x in accepts]

        if 'application/json' in accepts:
            return 'application/json'
        else:
            return ', '.join(accepts)

    def select_header_content_type(self, content_types):
        """
        Returns `Content-Type` based on an array of content_types provided.

        :param content_types: List of content-types.
        :return: Content-Type (e.g. application/json).
        """
        if not content_types:
            return 'application/json'

        content_types = [x.lower() for x in content_types]

        if 'application/json' in content_types or '*/*' in content_types:
            return 'application/json'
        else:
            return content_types[0]

    def __deserialize_file(self, response):
        """
        Saves response body into a file in a temporary folder,
        using the filename from the `Content-Disposition` header if provided.

        :param response:  RESTResponse.
        :return: file path.
        """

        fd, path = tempfile.mkstemp(dir=self.temp_folder_path)
        os.close(fd)
        os.remove(path)

        content_disposition = response.getheader("Content-Disposition")
        if content_disposition:
            filename = re.search(r'filename=[\'"]?([^\'"\s]+)[\'"]?',
                                 content_disposition).group(1)
            path = os.path.join(os.path.dirname(path), filename)

        with open(path, "w") as f:
            f.write(response.data)

        return path

    def __deserialize_primitive(self, data, klass):
        """
        Deserializes string to primitive type.

        :param data: str.
        :param klass: class literal.

        :return: int, long, float, str, bool.
        """
        try:
            return klass(data)
        except UnicodeEncodeError:
            return str(data)
        except TypeError:
            return data

    def __deserialize_object(self, value):
        """
        Return a original value.

        :return: object.
        """
        return value

    def __deserialize_date(self, string):
        """
        Deserializes string to date.

        :param string: str.
        :return: date.
        """
        try:
            return parse(string).date()
        except ImportError:
            return string
        except ValueError:
            raise ApiException(
                status=0,
                reason="Failed to parse `{0}` into a date object".format(
                    string))

    def __deserialize_datatime(self, string):
        """
        Deserializes string to datetime.

        The string should be in iso8601 datetime format.

        :param string: str.
        :return: datetime.
        """
        try:
            return parse(string)
        except ImportError:
            return string
        except ValueError:
            raise ApiException(
                status=0,
                reason=("Failed to parse `{0}` into a datetime object".format(
                    string)))

    def __deserialize_model(self, data, klass):
        """
        Deserializes list or dict to model.

        :param data: dict, list.
        :param klass: class literal.
        :return: model object.
        """
        if 'EnumMeta' == type(klass).__name__:
            return klass(data)
        if not klass.swagger_types:
            return data

        if klass == QueryResultRecordType:
            record_type = data.get('_type')
            klass = getattr(schema_v1_5, record_type)

        kwargs = {}
        cls_tree = list(inspect.getmro(klass))
        cls_tree.remove(object)
        for cls in cls_tree:
            for attr, attr_type in iteritems(cls.swagger_types):
                if data is not None and cls.attribute_map[
                        attr] in data and isinstance(data, (list, dict)):
                    value = data[cls.attribute_map[attr]]
                    kwargs[attr] = self.__deserialize(value, attr_type)

        instance = None
        if hasattr(models, klass.__name__):
            instance = klass(**kwargs)
        else:
            instance = klass()
            for key in kwargs:
                setattr(instance, key, kwargs[key])

        return instance

    def _redact_headers(self, headers):
        redacted_headers = {}
        for key, value in headers.items():
            if key not in self._HEADERS_TO_REDACT:
                redacted_headers[key] = value
            else:
                redacted_headers[key] = "[REDACTED]"
        return redacted_headers

    def _do_log_headers(self, headers, type):
        self._logger.debug('%s headers: %s' %
                           (type, self._redact_headers(headers)))

    def _do_log_bodies(self, body, type):
        self._logger.debug('%s body: %s' % (type, body))
