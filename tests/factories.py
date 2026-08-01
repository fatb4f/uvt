from __future__ import annotations

import factory

from .models import CopierAnswers, LicenseName


class CopierAnswersFactory(factory.Factory[CopierAnswers]):
    """Generate unique, valid inputs for the Copier questionnaire."""

    class Meta:
        model = CopierAnswers

    distribution_name = factory.Sequence(lambda number: f"example-project-{number}")

    class Params:
        apache = factory.Trait(license_name=LicenseName.APACHE_2_0)
        publishing = factory.Trait(publish=True)
        distinct_import_name = factory.Trait(import_package_name="distinct_package")
