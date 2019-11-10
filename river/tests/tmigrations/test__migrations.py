import os
import sys
from datetime import datetime, timedelta
from unittest import skipUnless

import django
import six
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import override_settings
from hamcrest import assert_that, equal_to, has_length, has_item, is_not, less_than

from river.models import TransitionApproval
from river.models.factories import StateObjectFactory, WorkflowFactory, TransitionApprovalMetaFactory, PermissionObjectFactory, UserObjectFactory, TransitionMetaFactory
from river.tests.models import BasicTestModel
from river.tests.models.factories import BasicTestModelObjectFactory

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

from django.core.management import call_command
from django.test import TestCase

_author_ = 'ahmetdal'


def clean_migrations():
    for f in os.listdir("river/tests/volatile/river/"):
        if f != "__init__.py" and f != "__pycache__":
            os.remove(os.path.join("river/tests/volatile/river/", f))

    for f in os.listdir("river/tests/volatile/river_tests/"):
        if f != "__init__.py" and f != "__pycache__":
            os.remove(os.path.join("river/tests/volatile/river_tests/", f))


class MigrationTests(TestCase):
    """
    This is the case to detect missing migration issues like https://github.com/javrasya/django-river/issues/30
    """

    migrations_before = []
    migrations_after = []

    def setUp(self):
        """
            Remove migration file generated by test if there is any missing.
        """
        clean_migrations()

    def tearDown(self):
        """
            Remove migration file generated by test if there is any missing.
        """
        clean_migrations()

    @override_settings(MIGRATION_MODULES={"river": "river.tests.volatile.river"})
    def test_shouldCreateAllMigrations(self):
        for f in os.listdir("river/migrations"):
            if f != "__init__.py" and f != "__pycache__" and not f.endswith(".pyc"):
                open(os.path.join("river/tests/volatile/river/", f), 'wb').write(open(os.path.join("river/migrations", f), 'rb').read())

        self.migrations_before = list(filter(lambda f: f.endswith('.py') and f != '__init__.py', os.listdir('river/tests/volatile/river/')))

        out = StringIO()
        sys.stout = out

        call_command('makemigrations', 'river', stdout=out)

        self.migrations_after = list(filter(lambda f: f.endswith('.py') and f != '__init__.py', os.listdir('river/tests/volatile/river/')))

        assert_that(out.getvalue(), equal_to("No changes detected in app 'river'\n"))
        assert_that(self.migrations_after, has_length(len(self.migrations_before)))

    @override_settings(MIGRATION_MODULES={"tests": "river.tests.volatile.river_tests"})
    def test__shouldNotKeepRecreatingMigrationsWhenNoChange(self):
        call_command('makemigrations', 'tests')

        self.migrations_before = list(filter(lambda f: f.endswith('.py') and f != '__init__.py', os.listdir('river/tests/volatile/river_tests/')))

        out = StringIO()
        sys.stout = out

        call_command('makemigrations', 'tests', stdout=out)

        self.migrations_after = list(filter(lambda f: f.endswith('.py') and f != '__init__.py', os.listdir('river/tests/volatile/river_tests/')))

        assert_that(out.getvalue(), equal_to("No changes detected in app 'tests'\n"))
        assert_that(self.migrations_after, has_length(len(self.migrations_before)))

    @skipUnless(django.VERSION[0] < 2, "Is not able to run with new version of django")
    def test__shouldMigrateTransitionApprovalStatusToStringInDB(self):
        out = StringIO()
        sys.stout = out
        state1 = StateObjectFactory(label="state1")
        state2 = StateObjectFactory(label="state2")
        workflow = WorkflowFactory(initial_state=state1, content_type=ContentType.objects.get_for_model(BasicTestModel), field_name="my_field")

        transition_meta = TransitionMetaFactory.create(
            workflow=workflow,
            source_state=state1,
            destination_state=state2,
        )
        TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=transition_meta,
            priority=0
        )
        workflow_object = BasicTestModelObjectFactory()

        with connection.cursor() as cur:
            result = cur.execute("select status from river_transitionapproval where object_id=%s;" % workflow_object.model.pk).fetchall()
            assert_that(result[0][0], equal_to("pending"))

        call_command('migrate', 'river', '0004', stdout=out)

        with connection.cursor() as cur:
            schema = cur.execute("PRAGMA table_info('river_transitionapproval');").fetchall()
            status_col_type = list(filter(lambda column: column[1] == 'status', schema))[0][2]
            assert_that(status_col_type, equal_to("integer"))

            result = cur.execute("select status from river_transitionapproval where object_id=%s;" % workflow_object.model.pk).fetchall()
            assert_that(result[0][0], equal_to(0))

        call_command('migrate', 'river', '0005', stdout=out)

        with connection.cursor() as cur:
            schema = cur.execute("PRAGMA table_info('river_transitionapproval');").fetchall()
            status_col_type = list(filter(lambda column: column[1] == 'status', schema))[0][2]
            assert_that(status_col_type, equal_to("varchar(100)"))

            result = cur.execute("select status from river_transitionapproval where object_id=%s;" % workflow_object.model.pk).fetchall()
            assert_that(result[0][0], equal_to("pending"))

    @skipUnless(django.VERSION[0] < 2, "Is not able to run with new version of django")
    def test__shouldAssessIterationsForExistingApprovals(self):
        out = StringIO()
        sys.stout = out
        state1 = StateObjectFactory(label="state1")
        state2 = StateObjectFactory(label="state2")
        state3 = StateObjectFactory(label="state3")
        state4 = StateObjectFactory(label="state4")

        workflow = WorkflowFactory(initial_state=state1, content_type=ContentType.objects.get_for_model(BasicTestModel), field_name="my_field")
        transition_meta_1 = TransitionMetaFactory.create(
            workflow=workflow,
            source_state=state1,
            destination_state=state2,
        )

        transition_meta_2 = TransitionMetaFactory.create(
            workflow=workflow,
            source_state=state2,
            destination_state=state3,
        )

        transition_meta_3 = TransitionMetaFactory.create(
            workflow=workflow,
            source_state=state2,
            destination_state=state4,
        )

        meta_1 = TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=transition_meta_1,
            priority=0
        )
        meta_2 = TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=transition_meta_2,
            priority=0
        )

        meta_3 = TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=transition_meta_2,
            priority=1
        )

        meta_4 = TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=transition_meta_3,
            priority=0
        )

        workflow_object = BasicTestModelObjectFactory()

        with connection.cursor() as cur:
            result = cur.execute("""
                select 
                    river_transitionapproval.meta_id, 
                    iteration 
                from river_transitionapproval 
                inner join river_transition rt on river_transitionapproval.transition_id = rt.id  
                where river_transitionapproval.object_id=%s;
             """ % workflow_object.model.pk).fetchall()
            assert_that(result, has_length(4))
            assert_that(result, has_item(equal_to((meta_1.pk, 0))))
            assert_that(result, has_item(equal_to((meta_2.pk, 1))))
            assert_that(result, has_item(equal_to((meta_3.pk, 1))))
            assert_that(result, has_item(equal_to((meta_4.pk, 1))))

        call_command('migrate', 'river', '0006', stdout=out)

        with connection.cursor() as cur:
            schema = cur.execute("PRAGMA table_info('river_transitionapproval');").fetchall()
            columns = six.moves.map(lambda column: column[1], schema)
            assert_that(columns, is_not(has_item("iteration")))

        call_command('migrate', 'river', '0007', stdout=out)

        with connection.cursor() as cur:
            result = cur.execute("select meta_id, iteration from river_transitionapproval where object_id=%s;" % workflow_object.model.pk).fetchall()
            assert_that(result, has_length(4))
            assert_that(result, has_item(equal_to((meta_1.pk, 0))))
            assert_that(result, has_item(equal_to((meta_2.pk, 1))))
            assert_that(result, has_item(equal_to((meta_3.pk, 1))))
            assert_that(result, has_item(equal_to((meta_4.pk, 1))))

    @skipUnless(django.VERSION[0] < 2, "Is not able to run with new version of django")
    def test__shouldAssessIterationsForExistingApprovalsWhenThereIsCycle(self):
        out = StringIO()
        sys.stout = out

        authorized_permission1 = PermissionObjectFactory()
        authorized_permission2 = PermissionObjectFactory()
        authorized_user = UserObjectFactory(user_permissions=[authorized_permission1, authorized_permission2])

        cycle_state_1 = StateObjectFactory(label="cycle_state_1")
        cycle_state_2 = StateObjectFactory(label="cycle_state_2")
        cycle_state_3 = StateObjectFactory(label="cycle_state_3")
        off_the_cycle_state = StateObjectFactory(label="off_the_cycle_state")

        workflow = WorkflowFactory(initial_state=cycle_state_1, content_type=ContentType.objects.get_for_model(BasicTestModel), field_name="my_field")

        transition_meta_1 = TransitionMetaFactory.create(
            workflow=workflow,
            source_state=cycle_state_1,
            destination_state=cycle_state_2,
        )

        transition_meta_2 = TransitionMetaFactory.create(
            workflow=workflow,
            source_state=cycle_state_2,
            destination_state=cycle_state_3,
        )

        transition_meta_3 = TransitionMetaFactory.create(
            workflow=workflow,
            source_state=cycle_state_3,
            destination_state=cycle_state_1,
        )

        transition_meta_4 = TransitionMetaFactory.create(
            workflow=workflow,
            source_state=cycle_state_3,
            destination_state=off_the_cycle_state,
        )

        meta_1 = TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=transition_meta_1,
            priority=0,
            permissions=[authorized_permission1]
        )

        meta_21 = TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=transition_meta_2,
            priority=0,
            permissions=[authorized_permission1]
        )

        meta_22 = TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=transition_meta_2,
            priority=1,
            permissions=[authorized_permission2]
        )

        meta_3 = TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=transition_meta_3,
            priority=0,
            permissions=[authorized_permission1]
        )

        final_meta = TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=transition_meta_4,
            priority=0,
            permissions=[authorized_permission1]
        )

        workflow_object = BasicTestModelObjectFactory()

        assert_that(workflow_object.model.my_field, equal_to(cycle_state_1))
        workflow_object.model.river.my_field.approve(as_user=authorized_user)
        assert_that(workflow_object.model.my_field, equal_to(cycle_state_2))
        workflow_object.model.river.my_field.approve(as_user=authorized_user)
        assert_that(workflow_object.model.my_field, equal_to(cycle_state_2))
        workflow_object.model.river.my_field.approve(as_user=authorized_user)
        assert_that(workflow_object.model.my_field, equal_to(cycle_state_3))

        approvals = TransitionApproval.objects.filter(workflow=workflow, workflow_object=workflow_object.model)
        assert_that(approvals, has_length(5))

        workflow_object.model.river.my_field.approve(as_user=authorized_user, next_state=cycle_state_1)
        assert_that(workflow_object.model.my_field, equal_to(cycle_state_1))

        with connection.cursor() as cur:
            result = cur.execute("""
                            select 
                                river_transitionapproval.meta_id, 
                                iteration 
                            from river_transitionapproval 
                            inner join river_transition rt on river_transitionapproval.transition_id = rt.id  
                            where river_transitionapproval.object_id=%s;
                         """ % workflow_object.model.pk).fetchall()
            assert_that(result, has_length(10))
            assert_that(result, has_item(equal_to((meta_1.pk, 0))))
            assert_that(result, has_item(equal_to((meta_21.pk, 1))))
            assert_that(result, has_item(equal_to((meta_22.pk, 1))))
            assert_that(result, has_item(equal_to((meta_3.pk, 2))))
            assert_that(result, has_item(equal_to((final_meta.pk, 2))))
            assert_that(result, has_item(equal_to((meta_1.pk, 3))))
            assert_that(result, has_item(equal_to((meta_21.pk, 4))))
            assert_that(result, has_item(equal_to((meta_22.pk, 4))))
            assert_that(result, has_item(equal_to((meta_3.pk, 5))))
            assert_that(result, has_item(equal_to((final_meta.pk, 5))))

        call_command('migrate', 'river', '0006', stdout=out)

        with connection.cursor() as cur:
            schema = cur.execute("PRAGMA table_info('river_transitionapproval');").fetchall()
            columns = six.moves.map(lambda column: column[1], schema)
            assert_that(columns, is_not(has_item("iteration")))

        call_command('migrate', 'river', '0007', stdout=out)

        with connection.cursor() as cur:
            result = cur.execute("select meta_id, iteration from river_transitionapproval where object_id=%s;" % workflow_object.model.pk).fetchall()
            assert_that(result, has_length(10))
            assert_that(result, has_item(equal_to((meta_1.pk, 0))))
            assert_that(result, has_item(equal_to((meta_21.pk, 1))))
            assert_that(result, has_item(equal_to((meta_22.pk, 1))))
            assert_that(result, has_item(equal_to((meta_3.pk, 2))))
            assert_that(result, has_item(equal_to((final_meta.pk, 2))))
            assert_that(result, has_item(equal_to((meta_1.pk, 3))))
            assert_that(result, has_item(equal_to((meta_21.pk, 4))))
            assert_that(result, has_item(equal_to((meta_22.pk, 4))))
            assert_that(result, has_item(equal_to((meta_3.pk, 5))))
            assert_that(result, has_item(equal_to((final_meta.pk, 5))))

    @skipUnless(django.VERSION[0] < 2, "Is not able to run with new version of django")
    def test__shouldMigrationForIterationMustFinishInShortAmountOfTimeWithTooManyObject(self):
        out = StringIO()
        sys.stout = out
        state1 = StateObjectFactory(label="state1")
        state2 = StateObjectFactory(label="state2")
        state3 = StateObjectFactory(label="state3")
        state4 = StateObjectFactory(label="state4")

        workflow = WorkflowFactory(initial_state=state1, content_type=ContentType.objects.get_for_model(BasicTestModel), field_name="my_field")
        transition_meta_1 = TransitionMetaFactory.create(
            workflow=workflow,
            source_state=state1,
            destination_state=state1,
        )

        transition_meta_2 = TransitionMetaFactory.create(
            workflow=workflow,
            source_state=state2,
            destination_state=state3,
        )

        transition_meta_3 = TransitionMetaFactory.create(
            workflow=workflow,
            source_state=state2,
            destination_state=state4,
        )

        TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=transition_meta_1,
            priority=0
        )
        TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=transition_meta_2,
            priority=0
        )

        TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=transition_meta_2,
            priority=1
        )

        TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=transition_meta_3,
            priority=0
        )

        BasicTestModelObjectFactory.create_batch(250)

        call_command('migrate', 'river', '0006', stdout=out)

        before = datetime.now()
        call_command('migrate', 'river', '0007', stdout=out)
        after = datetime.now()
        assert_that(after - before, less_than(timedelta(minutes=5)))

    @skipUnless(django.VERSION[0] < 2, "Is not able to run with new version of django")
    def test__shouldAssessIterationsForExistingApprovalsWhenThereIsMoreAdvanceCycle(self):
        out = StringIO()
        sys.stout = out

        authorized_permission1 = PermissionObjectFactory()
        authorized_permission2 = PermissionObjectFactory()
        authorized_user = UserObjectFactory(user_permissions=[authorized_permission1, authorized_permission2])

        opn = StateObjectFactory(label="open")
        in_progress = StateObjectFactory(label="in_progress")
        resolved = StateObjectFactory(label="resolved")
        re_opened = StateObjectFactory(label="re_opened")
        closed = StateObjectFactory(label="closed")
        final = StateObjectFactory(label="final")

        workflow = WorkflowFactory(initial_state=opn, content_type=ContentType.objects.get_for_model(BasicTestModel), field_name="my_field")

        open_to_in_progress_transition = TransitionMetaFactory.create(
            workflow=workflow,
            source_state=opn,
            destination_state=in_progress,
        )

        in_progress_to_resolved_transition = TransitionMetaFactory.create(
            workflow=workflow,
            source_state=in_progress,
            destination_state=resolved
        )

        resolved_to_re_opened_transition = TransitionMetaFactory.create(
            workflow=workflow,
            source_state=resolved,
            destination_state=re_opened
        )

        re_opened_to_in_progress_transition = TransitionMetaFactory.create(
            workflow=workflow,
            source_state=re_opened,
            destination_state=in_progress
        )

        resolved_to_closed_transition = TransitionMetaFactory.create(
            workflow=workflow,
            source_state=resolved,
            destination_state=closed
        )

        closed_to_final_transition = TransitionMetaFactory.create(
            workflow=workflow,
            source_state=closed,
            destination_state=final
        )

        open_to_in_progress = TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=open_to_in_progress_transition,
            priority=0,
            permissions=[authorized_permission1]
        )

        in_progress_to_resolved = TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=in_progress_to_resolved_transition,
            priority=0,
            permissions=[authorized_permission1]
        )

        resolved_to_re_opened = TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=resolved_to_re_opened_transition,
            priority=0,
            permissions=[authorized_permission2]
        )

        re_opened_to_in_progress = TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=re_opened_to_in_progress_transition,
            priority=0,
            permissions=[authorized_permission1]
        )

        resolved_to_closed = TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=resolved_to_closed_transition,
            priority=0,
            permissions=[authorized_permission1]
        )

        closed_to_final = TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=closed_to_final_transition,
            priority=0,
            permissions=[authorized_permission1]
        )

        workflow_object = BasicTestModelObjectFactory()

        assert_that(workflow_object.model.my_field, equal_to(opn))
        workflow_object.model.river.my_field.approve(as_user=authorized_user)
        assert_that(workflow_object.model.my_field, equal_to(in_progress))
        workflow_object.model.river.my_field.approve(as_user=authorized_user)
        assert_that(workflow_object.model.my_field, equal_to(resolved))
        workflow_object.model.river.my_field.approve(as_user=authorized_user, next_state=re_opened)
        assert_that(workflow_object.model.my_field, equal_to(re_opened))
        workflow_object.model.river.my_field.approve(as_user=authorized_user)
        assert_that(workflow_object.model.my_field, equal_to(in_progress))

        with connection.cursor() as cur:
            result = cur.execute("""
                            select 
                                river_transitionapproval.meta_id, 
                                iteration 
                            from river_transitionapproval 
                            inner join river_transition rt on river_transitionapproval.transition_id = rt.id  
                            where river_transitionapproval.object_id=%s;
                         """ % workflow_object.model.pk).fetchall()
            assert_that(result, has_length(11))
            assert_that(result, has_item(equal_to((open_to_in_progress.pk, 0))))
            assert_that(result, has_item(equal_to((in_progress_to_resolved.pk, 1))))
            assert_that(result, has_item(equal_to((resolved_to_closed.pk, 2))))
            assert_that(result, has_item(equal_to((resolved_to_re_opened.pk, 2))))
            assert_that(result, has_item(equal_to((re_opened_to_in_progress.pk, 3))))
            assert_that(result, has_item(equal_to((closed_to_final.pk, 3))))
            assert_that(result, has_item(equal_to((in_progress_to_resolved.pk, 4))))
            assert_that(result, has_item(equal_to((resolved_to_closed.pk, 5))))
            assert_that(result, has_item(equal_to((resolved_to_re_opened.pk, 5))))
            assert_that(result, has_item(equal_to((re_opened_to_in_progress.pk, 6))))
            assert_that(result, has_item(equal_to((closed_to_final.pk, 6))))

        call_command('migrate', 'river', '0006', stdout=out)

        with connection.cursor() as cur:
            schema = cur.execute("PRAGMA table_info('river_transitionapproval');").fetchall()
            columns = six.moves.map(lambda column: column[1], schema)
            assert_that(columns, is_not(has_item("iteration")))

        call_command('migrate', 'river', '0007', stdout=out)

        with connection.cursor() as cur:
            result = cur.execute("select meta_id, iteration from river_transitionapproval where object_id=%s;" % workflow_object.model.pk).fetchall()
            assert_that(result, has_length(11))
            assert_that(result, has_item(equal_to((open_to_in_progress.pk, 0))))
            assert_that(result, has_item(equal_to((in_progress_to_resolved.pk, 1))))
            assert_that(result, has_item(equal_to((resolved_to_closed.pk, 2))))
            assert_that(result, has_item(equal_to((resolved_to_re_opened.pk, 2))))
            assert_that(result, has_item(equal_to((re_opened_to_in_progress.pk, 3))))
            assert_that(result, has_item(equal_to((closed_to_final.pk, 3))))
            assert_that(result, has_item(equal_to((in_progress_to_resolved.pk, 4))))
            assert_that(result, has_item(equal_to((resolved_to_closed.pk, 5))))
            assert_that(result, has_item(equal_to((resolved_to_re_opened.pk, 5))))
            assert_that(result, has_item(equal_to((re_opened_to_in_progress.pk, 6))))
            assert_that(result, has_item(equal_to((closed_to_final.pk, 6))))

    @skipUnless(django.VERSION[0] < 2, "Is not able to run with new version of django")
    def test__shouldCreateTransitionsAndTransitionMetasOutOfApprovalMetaAndApprovals(self):
        out = StringIO()
        sys.stout = out
        state1 = StateObjectFactory(label="state1")
        state2 = StateObjectFactory(label="state2")
        state3 = StateObjectFactory(label="state3")
        state4 = StateObjectFactory(label="state4")

        workflow = WorkflowFactory(initial_state=state1, content_type=ContentType.objects.get_for_model(BasicTestModel), field_name="my_field")
        transition_1 = TransitionMetaFactory.create(workflow=workflow, source_state=state1, destination_state=state2)
        transition_2 = TransitionMetaFactory.create(workflow=workflow, source_state=state2, destination_state=state3)
        transition_3 = TransitionMetaFactory.create(workflow=workflow, source_state=state2, destination_state=state4)

        meta_1 = TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=transition_1,
            priority=0
        )
        meta_2 = TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=transition_2,
            priority=0
        )

        meta_3 = TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=transition_2,
            priority=1
        )

        meta_4 = TransitionApprovalMetaFactory.create(
            workflow=workflow,
            transition_meta=transition_3,
            priority=0
        )

        workflow_object = BasicTestModelObjectFactory()

        with connection.cursor() as cur:
            result = cur.execute("select id, transition_meta_id from river_transitionapprovalmeta;").fetchall()
            assert_that(result, has_length(4))
            assert_that(result, has_item(equal_to((meta_1.pk, transition_1.pk))))
            assert_that(result, has_item(equal_to((meta_2.pk, transition_2.pk))))
            assert_that(result, has_item(equal_to((meta_3.pk, transition_2.pk))))
            assert_that(result, has_item(equal_to((meta_4.pk, transition_3.pk))))

            result = cur.execute("select id, transition_id from river_transitionapproval where object_id='%s';" % workflow_object.model.pk).fetchall()
            assert_that(result, has_length(4))
            assert_that(result, has_item(equal_to((meta_1.transition_approvals.first().pk, transition_1.transitions.first().pk))))
            assert_that(result, has_item(equal_to((meta_2.transition_approvals.first().pk, transition_2.transitions.first().pk))))
            assert_that(result, has_item(equal_to((meta_3.transition_approvals.first().pk, transition_2.transitions.first().pk))))
            assert_that(result, has_item(equal_to((meta_4.transition_approvals.first().pk, transition_3.transitions.first().pk))))

        call_command('migrate', 'river', '0009', stdout=out)

        with connection.cursor() as cur:
            schema = cur.execute("PRAGMA table_info('river_transitionapprovalmeta');").fetchall()
            columns = [column[1] for column in schema]
            assert_that(columns, is_not(has_item("transition_meta_id")))
            assert_that(columns, has_item("source_state_id"))
            assert_that(columns, has_item("destination_state_id"))

            schema = cur.execute("PRAGMA table_info('river_transitionapproval');").fetchall()
            columns = [column[1] for column in schema]
            assert_that(columns, is_not(has_item("transition_id")))
            assert_that(columns, has_item("source_state_id"))
            assert_that(columns, has_item("destination_state_id"))

        call_command('migrate', 'river', '0010', stdout=out)

        with connection.cursor() as cur:
            schema = cur.execute("PRAGMA table_info('river_transitionapprovalmeta');").fetchall()
            columns = six.moves.map(lambda column: column[1], schema)
            assert_that(columns, has_item("transition_meta_id"))
            assert_that(columns, is_not(has_item("source_state_id")))
            assert_that(columns, is_not(has_item("destination_state_id")))

            schema = cur.execute("PRAGMA table_info('river_transitionapproval');").fetchall()
            columns = [column[1] for column in schema]
            assert_that(columns, has_item("transition_id"))
            assert_that(columns, is_not(has_item("source_state_id")))
            assert_that(columns, is_not(has_item("destination_state_id")))

        with connection.cursor() as cur:
            result = cur.execute("select id, transition_meta_id from river_transitionapprovalmeta;").fetchall()
            assert_that(result, has_length(4))
            assert_that(result, has_item(equal_to((meta_1.pk, transition_1.pk))))
            assert_that(result, has_item(equal_to((meta_2.pk, transition_2.pk))))
            assert_that(result, has_item(equal_to((meta_3.pk, transition_2.pk))))
            assert_that(result, has_item(equal_to((meta_4.pk, transition_3.pk))))

            result = cur.execute("select id, transition_id from river_transitionapproval where object_id='%s';" % workflow_object.model.pk).fetchall()
            assert_that(result, has_length(4))
            assert_that(result, has_item(equal_to((meta_1.transition_approvals.first().pk, transition_1.transitions.first().pk))))
            assert_that(result, has_item(equal_to((meta_2.transition_approvals.first().pk, transition_2.transitions.first().pk))))
            assert_that(result, has_item(equal_to((meta_3.transition_approvals.first().pk, transition_2.transitions.first().pk))))
            assert_that(result, has_item(equal_to((meta_4.transition_approvals.first().pk, transition_3.transitions.first().pk))))
