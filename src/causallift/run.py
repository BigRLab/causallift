# Copyright 2018-2019 QuantumBlack Visual Analytics Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND
# NONINFRINGEMENT. IN NO EVENT WILL THE LICENSOR OR OTHER CONTRIBUTORS
# BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF, OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
# The QuantumBlack Visual Analytics Limited ("QuantumBlack") name and logo
# (either separately or in combination, "QuantumBlack Trademarks") are
# trademarks of QuantumBlack. The License does not grant you any right or
# license to the QuantumBlack Trademarks. You may not use the QuantumBlack
# Trademarks or any confusingly similar mark as a trademark for your product,
#     or use the QuantumBlack Trademarks in any other manner that might cause
# confusion in the marketplace, including but not limited to in advertising,
# on websites, or on software.
#
# See the License for the specific language governing permissions and
# limitations under the License.

"""Application entry point."""

import logging.config
from pathlib import Path
from typing import Iterable, Type, Union
from warnings import warn

from kedro.cli.utils import KedroCliError
from kedro.config import ConfigLoader, MissingConfigException
from kedro.context import KedroContext, KedroContextError
from kedro.io import DataCatalog
from kedro.runner import AbstractRunner, ParallelRunner, SequentialRunner
from kedro.utils import load_obj
from kedro.pipeline import Pipeline

from causallift.pipeline import create_pipeline

from .default.logging import *
from typing import Dict, Any

import logging
log = logging.getLogger(__name__)


class ProjectContext(KedroContext):
    """Users can override the remaining methods from the parent class here, or create new ones
    (e.g. as required by plugins)

    """

    project_name = "CausalLift"
    project_version = "0.15.0"

    @property
    def pipeline(self) -> Pipeline:
        return create_pipeline()

    def run(
        self,
        tags: Iterable[str] = None,
        runner: AbstractRunner = None,
        node_names: Iterable[str] = None,
        only_missing: bool = False,
    ) -> Dict[str, Any]:
        """Runs the pipeline wi th a specified runner.

        Args:
            tags: An optional list of node tags which should be used to
                filter the nodes of the ``Pipeline``. If specified, only the nodes
                containing *any* of these tags will be run.
            runner: An optional parameter specifying the runner that you want to run
                the pipeline with.
            node_names: An optional list of node names which should be used to
                filter the nodes of the ``Pipeline``. If specified, only the nodes
                with these names will be run.
            only_missing: An option to run only missing nodes.
        Raises:
            KedroContextError: If the resulting ``Pipeline`` is empty
                or incorrect tags are provided.
        Returns:
            Any node outputs that cannot be processed by the ``DataCatalog``.
            These are returned in a dictionary, where the keys are defined
            by the node outputs.
        """
        # Report project name
        logging.info("** Kedro project {}".format(self.project_path.name))

        # Load the pipeline
        pipeline = self.pipeline
        if node_names:
            pipeline = pipeline.only_nodes(*node_names)
        if tags:
            pipeline = pipeline.only_nodes_with_tags(*tags)

        if not pipeline.nodes:
            msg = "Pipeline contains no nodes"
            if tags:
                msg += " with tags: {}".format(str(tags))
            raise KedroContextError(msg)

        # Run the runner
        runner = runner or SequentialRunner()
        if only_missing:
            return runner.run_only_missing(pipeline, self.catalog)
        else:
            return runner.run(pipeline, self.catalog)


class ProjectContext1(ProjectContext):
    r"Allow to specify runner by string."
    def run(self, runner: Union[AbstractRunner, str] = None, **kwargs) -> Dict[str, Any]:
        if isinstance(runner, str):
            assert runner in {"ParallelRunner", "SequentialRunner"}
            runner = ParallelRunner() if runner == "ParallelRunner" else SequentialRunner()
        return super().run(runner=runner, **kwargs)


class ProjectContext2(ProjectContext1):
    r"Keep the output datasets in the catalog."
    def run(self, **kwargs) -> Dict[str, Any]:
        d = super().run(**kwargs)
        self.catalog.add_feed_dict(d, replace=True)
        return d


class ProjectContext3(ProjectContext2):
    r"Allow to overwrite the default logging config and remove yaml file dependency."
    def __init__(self, logging_config: Dict = None):
        self._project_path = Path().cwd().resolve()
        logging_config = logging_config or conf_logging_()
        logging.config.dictConfig(logging_config)
        self._catalog = DataCatalog()


class ProjectContext4(ProjectContext3):
    r"Overwrite the default runner and only_missing option for the run."
    def __init__(self, runner: str = None, only_missing: bool = False, **kwargs):
        super().__init__(**kwargs)
        self._runner = runner
        self._only_missing = only_missing
    def run(self, runner: str = None, only_missing: bool = False, **kwargs) -> Dict[str, Any]:
        runner = runner or self._runner
        only_missing = only_missing or self._only_missing
        log.info('[Run option] runner: {}, run_only_missing: {}'.format(runner, only_missing))
        return super().run(runner=runner, only_missing=only_missing, **kwargs)


class FlexibleProjectContext(ProjectContext4):
    r"Keep the keyword arguments in the same order as ProjectContext."
    def run(
        self,
        tags: Iterable[str] = None,
        runner: AbstractRunner = None,
        node_names: Iterable[str] = None,
        only_missing: bool = False,
    ) -> Dict[str, Any]:
        return super().run(tags=tags, runner=runner, node_names=node_names,
                           only_missing=only_missing)


def __kedro_context__(env: str = None, **kwargs) -> KedroContext:
    """Provide this project's context to ``kedro`` CLI and plugins.
    Please do not rename or remove, as this will break the CLI tool.

    Plugins may request additional objects from this method.

    Args:
        env: An optional parameter specifying the environment in which
        the ``Pipeline`` should be run. If not specified defaults to "local".
        kwargs: Optional custom arguments defined by users.
    Returns:
        Instance of ProjectContext class defined in Kedro project.

    """
    if env is None:
        # Default configuration environment to be used for running the pipeline.
        # Change this constant value if you want to load configuration
        # from a different location.
        env = "local"

    return ProjectContext(Path.cwd(), env, **kwargs)


def main(
    tags: Iterable[str] = None, env: str = None, runner: Type[AbstractRunner] = None
):
    """Application main entry point.

    Args:
        tags: An optional list of node tags which should be used to
            filter the nodes of the ``Pipeline``. If specified, only the nodes
            containing *any* of these tags will be added to the ``Pipeline``.
        env: An optional parameter specifying the environment in which
            the ``Pipeline`` should be run. If not specified defaults to "local".
        runner: An optional parameter specifying the runner that you want to run
            the pipeline with.

    """

    context = __kedro_context__(env)
    context.run(tags, runner)


if __name__ == "__main__":
    main()
