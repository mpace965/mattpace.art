"""User sketch modules."""

from sketchbook.steps.output_bundle import OutputBundle


class SiteOutputBundle(OutputBundle):
    """OutputBundle for the 'bundle' bundle.

    Use this in place of OutputBundle when marking a node for the default
    build. Pipe it in like any other step:

        blended.pipe(SiteOutputBundle)
    """

    def __init__(self) -> None:
        super().__init__("bundle")


__all__ = ["SiteOutputBundle"]
