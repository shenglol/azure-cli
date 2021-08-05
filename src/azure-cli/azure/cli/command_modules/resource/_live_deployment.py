import time
import abc

from rich.live import Live
from rich.table import Column, Table, box


class LiveDeploymentLongRunningOperation(metaclass=abc.ABCMeta):  # pylint: disable=too-few-public-methods
    def __init__(self, mgmt_resource_client, what_if_result, refresh_interval):
        self._mgmt_resource_client = mgmt_resource_client
        self._resource_statuses = [
            [x.resource_id, f"to {x.change_type}"] for x in what_if_result.changes if x.change_type.lower() != "ignore"
        ]
        self._refresh_interval = refresh_interval

    @abc.abstractmethod
    def _refresh_resource_statuses(self):
        return

    def _delay(self):
        time.sleep(self._refresh_interval)

    def _generate_resource_statuses_table(self):
        table = Table(
            Column(header="Resource Name", no_wrap=True),
            Column(header="Status", no_wrap=True, justify="right"),
            box=box.SIMPLE,
            header_style="bold blue",
            caption_style="bold",
            min_width=80,
        )

        for (resource_id, status) in self._resource_statuses:
            table.add_row(resource_id.split("/")[-1], status)

        return table

    def __call__(self, poller):
        from msrest.exceptions import ClientException
        from azure.core.exceptions import HttpResponseError

        with Live(self._generate_resource_statuses_table(), auto_refresh=False) as live:
            while not poller.done():
                self._delay()
                self._refresh_resource_statuses()
                live.update(self._generate_resource_statuses_table(), refresh=True)

        try:
            poller.result()
        except (ClientException, HttpResponseError) as exception:
            from azure.cli.core.commands.arm import handle_long_running_operation_exception
            if isinstance(exception, ClientException):
                handle_long_running_operation_exception(exception)
            else:
                raise exception

        return None


class LiveResourceGroupDeploymentLongRunningOperation(
    LiveDeploymentLongRunningOperation
):  # pylint: disable=too-few-public-methods
    def __init__(self, resource_group_name, deployment_name, mgmt_resource_client, what_if_result, refresh_interval=1):
        super().__init__(mgmt_resource_client, what_if_result, refresh_interval)

        self._resource_group_name = resource_group_name
        self._deployment_name = deployment_name

    def _refresh_resource_statuses(self):
        deployment_operations = self._mgmt_resource_client.deployment_operations.list(
            self._resource_group_name, self._deployment_name
        )

        for deployment_operation in deployment_operations:
            if deployment_operation.properties.target_resource:
                for resource_status in self._resource_statuses:
                    if resource_status[0] == deployment_operation.properties.target_resource.id:
                        resource_status[1] = deployment_operation.properties.provisioning_state

        return self._resource_statuses
