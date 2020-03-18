import time
from datetime import datetime, timedelta
from enum import Enum
from vcd.client.exceptions import TaskTimeoutException, VcdTaskException
from vcloud.api.rest.schema_v1_5.task_type import TaskType


class TaskStatus(Enum):
    QUEUED = 'queued'
    PRE_RUNNING = 'preRunning'
    RUNNING = 'running'
    SUCCESS = 'success'
    ERROR = 'error'
    CANCELED = 'canceled'
    ABORTED = 'aborted'


class TaskMonitor(object):
    _DEFAULT_POLL_SEC = 5
    _DEFAULT_TIMEOUT_SEC = 600

    def __init__(self, client, logger):
        self._client = client
        self._logger = logger

    def wait_for_success(self,
                         task,
                         timeout=_DEFAULT_TIMEOUT_SEC,
                         poll_frequency=_DEFAULT_POLL_SEC,
                         callback=None):
        return self.wait_for_status(task,
                                    timeout,
                                    poll_frequency, [TaskStatus.ERROR],
                                    [TaskStatus.SUCCESS],
                                    callback=callback)

    def wait_for_status(self,
                        task,
                        timeout=_DEFAULT_TIMEOUT_SEC,
                        poll_frequency=_DEFAULT_POLL_SEC,
                        fail_on_statuses=[
                            TaskStatus.ABORTED, TaskStatus.CANCELED,
                            TaskStatus.ERROR
                        ],
                        expected_target_statuses=[TaskStatus.SUCCESS],
                        callback=None):
        """Waits for task to reach expected status.

        :param Task task: Task returned by post or put calls.
        :param float timeout: Time (in seconds, floating point, fractional)
            to wait for task to finish.
        :param float poll_frequency: time (in seconds, as above) with which
            task will be polled.
        :param list fail_on_statuses: method will raise an exception if any
            of the TaskStatus in this list is reached. If this parameter is
            None then either task will achieve expected target status or throw
            TimeOutException.
        :param list expected_target_statuses: list of expected target
            status.
        :return: Task we were waiting for
        :rtype Task:
        :raises TimeoutException: If task is not finished within given time.
        :raises VcdException: If task enters a status in fail_on_statuses list
        """
        if fail_on_statuses is None:
            _fail_on_statuses = []
        elif isinstance(fail_on_statuses, TaskStatus):
            _fail_on_statuses[fail_on_statuses]
        else:
            _fail_on_statuses = fail_on_statuses
        task_href = task.href
        start_time = datetime.now()
        self._logger.debug('Waiting for task: ' + task.operation)
        while True:
            task = self._get_task(task_href)
            self._logger.debug('Task status: ' + task.status)
            if callback is not None:
                callback(task)
            task_status = task.status.lower()
            for status in expected_target_statuses:
                if task_status == status.value.lower():
                    return task
            for status in _fail_on_statuses:
                if task_status == status.value.lower():
                    raise VcdTaskException(task_status, task.error)
            if start_time - datetime.now() > timedelta(seconds=timeout):
                break
            time.sleep(poll_frequency)
        raise TaskTimeoutException("Task timeout")

    def _get_task(self, task_href):
        return self._client.get_resource(href=task_href,
                                         response_type=TaskType)
