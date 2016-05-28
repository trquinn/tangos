import halo_db as db
from halo_db.simulation_output_handlers import testing
from halo_db.tools import crosslink, add_simulation
from halo_db import log, parallel_tasks, live_calculation
from nose.tools import assert_raises
import os, os.path

def setup():
    parallel_tasks.use('null')
    db.init_db("sqlite://")
    db.config.base = os.path.join(os.path.dirname(__name__), "test_simulations")
    manager = add_simulation.SimulationAdderUpdater(testing.TestOutputSetHandler("dummy_sim_1"))
    manager2 = add_simulation.SimulationAdderUpdater(testing.TestOutputSetHandler("dummy_sim_2"))
    with log.LogCapturer():
        manager.scan_simulation_and_add_all_descendants()
        manager2.scan_simulation_and_add_all_descendants()

def test_timestep_linking():
    tl = crosslink.TimeLinker()
    tl.parse_command_line([])
    with log.LogCapturer():
        tl.run_calculation_loop()
    assert db.get_halo("dummy_sim_1/step.1/1").next==db.get_halo("dummy_sim_1/step.2/1")
    assert db.get_halo("dummy_sim_1/step.2/2").previous == db.get_halo("dummy_sim_1/step.1/2")
    assert db.get_halo("dummy_sim_1/step.1/1").links.count()==2

def test_crosslinking():
    cl = crosslink.CrossLinker()
    cl.parse_command_line(["dummy_sim_2","dummy_sim_1"])

    with log.LogCapturer():
        assert cl.need_crosslink_ts(db.get_timestep("dummy_sim_1/step.1"), db.get_timestep("dummy_sim_2/step.1"))
        cl.run_calculation_loop()
        assert not cl.need_crosslink_ts(db.get_timestep("dummy_sim_1/step.1"), db.get_timestep("dummy_sim_2/step.1"))

    assert db.get_halo('dummy_sim_1/step.1/1').calculate('match("dummy_sim_2").dbid()')==db.get_halo('dummy_sim_2/step.1/1').id
    assert db.get_halo('dummy_sim_2/step.2/3').calculate('match("dummy_sim_1").dbid()') == db.get_halo(
        'dummy_sim_1/step.2/3').id

    with assert_raises(live_calculation.NoResultsError):
        result = db.get_halo('dummy_sim_2/step.3/1').calculate('match("dummy_sim_1").dbid()')