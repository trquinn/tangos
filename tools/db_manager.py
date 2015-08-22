#!/usr/bin/env python

import localset
import numpy as np
import pynbody
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from halo_db import internal_session, Simulation, TimeStep, get_or_create_dictionary_item, SimulationProperty, \
    Halo, Base, Creator, all_simulations, get_simulation, TrackData, HaloProperty, HaloLink, get_halo
import halo_db as db
import sys
import terminalcontroller
from terminalcontroller import term
import glob



def add_simulation_timesteps_gadget(basename, reassess=False):

    steps = set(glob.glob(basename+"/snapshot_???"))
    print steps
    sim = internal_session.query(Simulation).filter_by(
        basename=basename).first()
    if sim is None:
        sim = Simulation(basename)
        internal_session.add(sim)
        print term.RED + "Add gadget simulation:", sim, term.NORMAL
    else:
        print term.GREEN + "Simulation exists:", sim, term.NORMAL
    internal_session.commit()
    steps_existing = set([ttt.relative_filename for ttt in sim.timesteps])
    add_ts = []

    for s in steps.union(steps_existing):
        ex = internal_session.query(TimeStep).filter_by(
            simulation=sim, extension=strip_slashes(s[len(basename):])).first()
        if ex != None:
            print term.GREEN, "Timestep exists: ", ex, term.NORMAL
        else:
            ex = TimeStep(sim, strip_slashes(s[len(basename):]))
            print term.RED, "Add timestep:", ex, term.NORMAL
            add_ts.append(ex)

    internal_session.add_all(add_ts)
    for ts in add_ts:
        add_halos(ts)
    internal_session.commit()


def add_simulation_timesteps_ramses(basename, reassess=False):
    from terminalcontroller import term

    outputs = glob.glob(basename + "/output_00*")
    sim = internal_session.query(Simulation).filter_by(
        basename=basename).first()
    if sim is None:
        sim = Simulation(basename)
        internal_session.add(sim)
        print term.RED + "Add ramses simulation:", sim, term.NORMAL
    else:
        print term.GREEN + "Simulation exists:", sim, term.NORMAL

    internal_session.commit()

    steps = set(glob.glob(basename + "/output_00???"))
    steps_existing = set([ttt.relative_filename for ttt in sim.timesteps])

    add_ts = []

    for s in steps.union(steps_existing):
        ex = internal_session.query(TimeStep).filter_by(
            simulation=sim, extension=strip_slashes(s[len(basename):])).first()
        if ex != None:
            print term.GREEN, "Timestep exists: ", ex, term.NORMAL
        else:
            ex = TimeStep(sim, strip_slashes(s[len(basename):]))
            print term.RED, "Add timestep:", ex, term.NORMAL
            add_ts.append(ex)

    internal_session.add_all(add_ts)
    internal_session.commit()

    prop_dict = {}

    nmls = glob.glob(localset.base + basename + "/*.nml")
    if len(nmls) > 1:
        print "Too many nmls - ignoring"
    elif len(nmls) == 0:
        print "No nmls"
    else:
        f = open(nmls[0])
        store_next = None
        for l in f:
            if store_next is not None:
                x = l.split("=")[1].split(",")
                x = map(lambda y: float(y.strip()), x)
                for k, v in zip(store_next, x):
                    if k != "_":
                        prop_dict[k] = v
                store_next = None
            if l.startswith("!halo_db:"):
                store_next = map(str.strip, l[9:].split(","))

    for k in prop_dict:

        dict_k = get_or_create_dictionary_item(internal_session, k)

        x = sim.properties.filter_by(name=dict_k).first()
        if x is not None:
            print term.GREEN, "Simulation property exists: ", x, term.NORMAL
        else:
            print dict_k, prop_dict[k]
            x = SimulationProperty(sim, dict_k, prop_dict[k])
            print term.RED, "Create simulation property: ", x, term.NORMAL
            internal_session.add(x)

    internal_session.commit()


def add_halos(ts,max_gp=1000):
    from terminalcontroller import term
    #if ts.halos.filter_by(halo_type=0).count() > 0:
    #    print term.GREEN, "  Halos already exist for", ts, term.NORMAL
    #    return

    if not add_halos_from_stat(ts):
        print term.YELLOW, "  -- deriving from halo catalogue instead of .stat file (slower)", ts, term.NORMAL
        s = ts.filename
        f = ts.load()
        h = f.halos()
        if hasattr(h, 'precalculate'):
            h.precalculate()
        for i in xrange(1, max_gp):
            try:
                hi = h[i]
                if (not ts.halos.filter_by(halo_type=0, halo_number=i).count()>0) and len(hi.dm) > 1000:
                    hobj = Halo(ts, i, len(hi.dm), len(hi.star), len(hi.gas))
                    internal_session.add(hobj)
            except (ValueError, KeyError) as e:
                pass


def add_halos_from_stat(ts):
    from terminalcontroller import term
    s = ts.filename
    try:
        f = file(s + ".amiga.stat")
    except IOError:
        print term.YELLOW, "  No .stat file found for", ts, term.NORMAL
        return False
    header = f.readline().split()
    gid_id = header.index("Grp")
    NGas_id = header.index("N_gas")
    NStar_id = header.index("N_star")
    NDM_id = header.index("N_dark")
    for l in f:
        s = l.split()
        if int(s[NDM_id]) > 1000:
            h = Halo(ts, int(s[gid_id]), int(s[NDM_id]), int(
                s[NStar_id]), int(s[NGas_id]))
            internal_session.add(h)
    return True


def strip_slashes(name):
    """Strip trailing and leading slashes from relative path"""
    while name[0] == "/":
        name = name[1:]
    while name[-1] == "/":
        name = name[:-1]
    return name


def add_simulation_timesteps(options):
    reassess=False
    basename = options.sim

    if len(glob.glob(localset.base + basename + "/output_00*")) > 0:
        add_simulation_timesteps_ramses(basename, reassess)
        return

    if len(glob.glob(localset.base + basename + "/snapshot_???"))>0:
        add_simulation_timesteps_gadget(basename, reassess)
        return

    import magic_amiga
    from terminalcontroller import term, heading
    import pynbody
    import time

    flags_include = ["dPhysDenMin", "dCStar", "dTempMax",
                     "dESN", "bLowTCool", "bSelfShield", "dExtraCoolShutoff"]
    # check_extensions = ["amiga.grp", "iord"]
    # ["HI","amiga.grp","HeI","HeII","coolontime","iord"]
    check_extensions = []

    if basename[-1] == "/":
        basename = basename[:-1]

    steps = magic_amiga.find(None, basename=basename + "/", ignore=[])
    print steps
    # check whether simulation exists
    sim = internal_session.query(Simulation).filter_by(
        basename=basename).first()
    heading(basename)

    try:
        pfile = magic_amiga.get_param_file(basename + "/")
        print "Param file = ", pfile
        pfile_dict = magic_amiga.param_file_to_dict(pfile)
        prop_dict = {}
        log_fn = pfile_dict["achOutName"] + ".log"
        log_path = pfile.split("/")[:-1]
        log_path.append(log_fn)
        log_path = "/".join(log_path)
        print "Log file = ", log_path
    except RuntimeError:
        print term.BLUE, "! No param file found !", term.NORMAL
        pfile_dict = {}
        prop_dict = {}
        log_path = "None"

    try:
        if sim == None:
            sim = Simulation(basename)

            internal_session.add(sim)
            print term.RED + "Add simulation: ", sim, term.NORMAL
        else:
            print term.GREEN + "Simulation exists: ", sim, term.NORMAL

        steps_existing = set([ttt.relative_filename for ttt in sim.timesteps])

        for f in flags_include:
            if pfile_dict.has_key(f):
                prop_dict[f] = pfile_dict[f]

        try:
            f = file(log_path)
            for l in f:
                if "# Code compiled:" in l:
                    prop_dict["compiled"] = time.strptime(
                        l.split(": ")[1].strip(), "%b %d %Y %H:%M:%S")
                if "# Preprocessor macros: " in l:
                    prop_dict["macros"] = l.split(": ")[1].strip()
                    break
        except IOError:
            print term.BLUE, "Warning: No log file " + log_path, term.NORMAL
            pass

        for k in prop_dict:

            dict_k = get_or_create_dictionary_item(internal_session, k)

            x = sim.properties.filter_by(name=dict_k).first()
            if x is not None:
                print term.GREEN, "Simulation property exists: ", x, term.NORMAL
            else:
                print dict_k, prop_dict[k]
                x = SimulationProperty(sim, dict_k, prop_dict[k])
                print term.RED, "Create simulation property: ", x, term.NORMAL
                internal_session.add(x)

        for s in steps.union(steps_existing):
            problem = False
            ex = internal_session.query(TimeStep).filter_by(
                simulation=sim, extension=strip_slashes(s[len(basename):])).first()
            if ex != None:
                print term.GREEN, "Timestep exists: ", ex, term.NORMAL
                if reassess:

                    try:
                        f = pynbody.load(ex.filename, maxlevel=2)
                        length = len(f)
                        if abs(ex.time_gyr-pynbody.analysis.cosmology.age(f))>0.001:
                            ex.time_gyr = pynbody.analysis.cosmology.age(f)
                            print term.YELLOW, " Update: ", ex, term.NORMAL
                    except (IOError, RuntimeError):
                        problem = True
                        if not ex.available:
                            print term.YELLOW, " Problem loading", ex.filename, " - marking unavailable", term.NORMAL
                            ex.available = False

                    for ext in check_extensions:
                        try:
                            f = file(ex.filename + "." + ext)
                            ext_line = f.readline()
                        except IOError:
                            print term.YELLOW, " Extension " + ext + " missing or unreadable for file " + ex.filename + " - marking unavailable", term.NORMAL
                            ex.available = False
                            problem = True
                            break
                        if ext == "amiga.grp" and int(ext_line) != length:
                            print term.YELLOW, " Alyson's script has produced something of the wrong length for file " + ex.filename + "- marking unavailable", term.NORMAL
                            ex.available = False
                            problem = True
                            break

                    if not problem and not ex.available:
                        print term.YELLOW, " Simulation seems OK, marking as available", term.NORMAL
                        ex.available = True

                    if ex.halos.count()<2:
                        add_halos(ex)

            else:
                ex = None
                try:
                    ex = TimeStep(sim, strip_slashes(s[len(basename):]))
                    print term.RED, "Add timestep: ", ex, term.NORMAL

                    internal_session.add(ex)
                    print ex
                    try:
                        add_halos(ex)
                        internal_session.commit()
                    except Exception, e:
                        print term.RED, "ERROR", term.NORMAL, "while trying to add halos"
                        exc_type, exc_value, exc_traceback = sys.exc_info()
                        print e
                        traceback.print_tb(exc_traceback)
                        internal_session.rollback()



                except IOError, e:
                    print e
                    print term.BLUE, "Couldn't load timestep requested for adding", s, term.NORMAL
                    if ex != None:
                        internal_session.delete(ex)

    except:
        internal_session.rollback()
        raise

    internal_session.commit()


def db_import(remote_db, *sims):

    global _current_creator, internal_session
    engine2 = create_engine('sqlite:///' + remote_db, echo=False)
    ext_session = sessionmaker(bind=engine2)()

    _current_creator = internal_session.merge(_current_creator)

    _db_import_export(internal_session, ext_session, *sims)


def db_export(remote_db, *sims):

    global _current_creator, internal_session
    engine2 = create_engine('sqlite:///' + remote_db, echo=False)

    int_session = internal_session
    ext_session = sessionmaker(bind=engine2)()
    external_to_internal_halo_id = {}

    Base.metadata.create_all(engine2)

    _x_current_creator = _current_creator

    internal_session = ext_session
    _current_creator = ext_session.merge(Creator())

    _db_import_export(ext_session, int_session, *sims)

    _current_creator = _x_current_creator
    internal_session = int_session


def _db_import_export(target_session, from_session, *sims):
    from terminalcontroller import heading
    external_to_internal_halo_id = {}
    translated_halolink_ids = []

    if sims == tuple():
        sims = [x.id for x in all_simulations(from_session)]

    for sim in sims:
        ext_sim = get_simulation(sim, from_session)
        sim = Simulation(ext_sim.basename)
        heading("import " + repr(ext_sim))
        sim = target_session.merge(sim)

        for p_ext in ext_sim.properties:
            dic = get_or_create_dictionary_item(
                target_session, p_ext.name.text)
            p = SimulationProperty(sim, dic, p_ext.data)
            p = target_session.merge(p)

        for tk_ext in ext_sim.trackers:
            tk = TrackData(sim, tk_ext.halo_number)
            tk.particles = tk_ext.particles
            tk.use_iord = tk_ext.use_iord

        for ts_ext in ext_sim.timesteps:
            print ".",
            sys.stdout.flush()
            ts = TimeStep(sim, ts_ext.extension, False)
            ts.redshift = ts_ext.redshift
            ts.time_gyr = ts_ext.time_gyr
            ts.available = True
            ts = target_session.merge(ts)
            for h_ext in ts_ext.halos:
                h = Halo(ts, h_ext.halo_number, h_ext.NDM,
                         h_ext.NStar, h_ext.NGas, h_ext.halo_type)
                h = target_session.merge(h)
                assert h.id is not None and h.id > 0
                external_to_internal_halo_id[h_ext.id] = h.id
                for p_ext in h_ext.properties:
                    dic = get_or_create_dictionary_item(
                        target_session, p_ext.name.text)
                    dat = p_ext.data
                    if dat is not None:
                        p = HaloProperty(h, dic, dat)
                        p = target_session.merge(p)

        print "Translate halolinks",
        for ts_ext in ext_sim.timesteps:
            print ".",
            sys.stdout.flush()
            _translate_halolinks(
                target_session, ts_ext.links_from, external_to_internal_halo_id, translated_halolink_ids)
            _translate_halolinks(
                target_session, ts_ext.links_to, external_to_internal_halo_id, translated_halolink_ids)

        print "Done"
        target_session.commit()


def _translate_halolinks(target_session, halolinks, external_to_internal_halo_id, translated):
    for hl_ext in halolinks:
        if hl_ext.id in translated:
            continue

        dic = get_or_create_dictionary_item(
            target_session, hl_ext.relation.text)
        hl_new = HaloLink(None, None, dic)

        try:
            hl_new.halo_from_id = external_to_internal_halo_id[
                hl_ext.halo_from_id]
        except KeyError:
            continue

        try:
            hl_new.halo_to_id = external_to_internal_halo_id[hl_ext.halo_to_id]
        except KeyError:
            continue
        target_session.add(hl_new)
        translated.append(hl_ext.id)


def update_deprecation(opts):

    session = db.internal_session

    print "unmark all:",session.execute("update haloproperties set deprecated=0").rowcount
    print "      mark:",session.execute("update haloproperties set deprecated=1 where id in (SELECT min(id) FROM haloproperties GROUP BY halo_id, name_id HAVING COUNT(*)>1 ORDER BY halo_id, name_id)").rowcount

    session.commit()






def rem_simulation_timesteps(options):
    basename = options.sims
    from terminalcontroller import term

    sim = internal_session.query(Simulation).filter_by(
        basename=basename).first()

    if sim == None:
        print term.GREEN + "Simulation does not exist", term.NORMAL
    else:
        print term.RED + "Delete simulation", sim, term.NORMAL
        internal_session.delete(sim)


def add_tracker(halo, size=None):

    try:
        halo = get_halo(halo)
    except:

        sim = get_simulation(halo)
        print "Adding tracker for isolated run", sim
        halo = None

    if halo is not None:
        # check we can open the tracker file
        hfile = halo.load()
        hfile.physical_units()
        use_iord = True
        try:
            hfile.dm['iord']
        except:
            use_iord = False

        # get the centre

        cen = halo.get('SSC', None)
        if cen is None:
            cen = pynbody.analysis.halo.shrink_sphere_center(hfile.dm)

        hfile.ancestor.dm['pos'] -= cen

        if size is None:
            size = '500 pc'

        size = pynbody.units.Unit(size)
        try:
            size.in_units("kpc")
            X = hfile.ancestor.dm[pynbody.filt.Sphere(size)]
        except:
            size.in_units("kpc km s^-1")
            X = hfile.ancestor.dm[pynbody.filt.LowPass("j2", size ** 2)]
            size = str(size.in_units("kpc km s^-1")) + "_kks"

        if len(X) < 2:
            print "Alert! Track data is too short"
            import pdb
            pdb.set_trace()
        # setup the tracker
        tx = TrackData(halo.timestep.simulation)
        print "Tracker halo ID is", tx.halo_number
        print "Length of track data is", len(X)
        tx.select(X, use_iord)
        ts_trigger = halo.timestep
    else:
        f = sim.timesteps[0].load()
        tx = TrackData(sim)
        if tx.halo_number != 1:
            print "Already have a tracker for this simulation -> abort"
            return
        print "Tracker halo ID is", tx.halo_number
        tx.particles = np.array(
            np.arange(0, len(f.dm) - 1, 1), dtype=int)
        tx.use_iord = False
        ts_trigger = None

    internal_session.add(tx)
    tx.create_halos(ts_trigger)
    if halo is not None:
        targ = halo.timestep.halos.filter_by(
            halo_type=1, halo_number=tx.halo_number).first()
        size = str(size).replace(" ", "")
        halo["dm_central_" + size] = targ
        print "Copying SSC...",
        sys.stdout.flush()
        while halo is not None:
            try:
                targ['SSC'] = halo['SSC']
            except KeyError:
                pass
            halo = halo.next
            targ = targ.next
        print "done"
    internal_session.commit()


def grep_run(st):
    run = internal_session.query(Creator).filter(
        Creator.command_line.like("%" + st + "%")).all()
    for r in run:
        print r.id,


def list_recent_runs(opts):
    n = opts.num
    run = internal_session.query(Creator).order_by(
        Creator.id.desc()).limit(n).all()
    for r in run:
        r.print_info()


def rem_run(id, confirm=True):
    run = internal_session.query(Creator).filter_by(id=id).first()
    print "You want to delete everything created by the following run:"
    run.print_info()

    if confirm:
        print """>>> type "yes" to continue"""

    if (not confirm) or raw_input(":").lower() == "yes":
        for y in run.halolinks:
            internal_session.delete(y)
        internal_session.commit()
        internal_session.delete(run)
        internal_session.commit()
        print "OK"
    else:
        print "aborted"

def rollback(options):
    for run_id in options.ids:
        rem_run(run_id, not options.force)

if __name__ == "__main__":

    db.internal_session = db.BlockingSession(bind = db.engine)
    import argparse

    parser = argparse.ArgumentParser()
    db.supplement_argparser(parser)
    parser.add_argument("--verbose", action="store_true",
                        help="Print extra information")


    subparse = parser.add_subparsers()

    subparse_add = subparse.add_parser("add",
                                       help="Add new simulations to the database, or update existing simulations")
    subparse_add.add_argument("sim",action="store",
                              help="The path to the simulation folders relative to the database folder")
    subparse_add.set_defaults(func=add_simulation_timesteps)

    subparse_recentruns = subparse.add_parser("recent-runs",
                                              help="List information about the most recent database updates")
    subparse_recentruns.set_defaults(func=list_recent_runs)
    subparse_recentruns.add_argument("num",type=int,
                                     help="The number of runs to display, starting with the most recent")

    subparse_remruns = subparse.add_parser("rm", help="Remove a simulation from the database")
    subparse_remruns.add_argument("sims",help="The path to the simulation folder relative to the database folder")
    subparse_remruns.set_defaults(func=rem_simulation_timesteps)

    subparse_deprecate = subparse.add_parser("deprecate",
                                             help="Deactivate old copies of properties (if they are present)")
    subparse_deprecate.set_defaults(func=update_deprecation)

    subparse_rollback = subparse.add_parser("rollback", help="Remove database updates (by ID - see recent-runs)")
    subparse_rollback.add_argument("ids",nargs="*",type=int,help="IDs of the database updates to remove")
    subparse_rollback.add_argument("--force","-f",action="store_true",help="Do not prompt for confirmation")
    subparse_rollback.set_defaults(func=rollback)


    args = parser.parse_args()
    args.func(args)

    """

   
    if "verbose" in sys.argv:
        del sys.argv[sys.argv.index("verbose")]
    if "db-verbose" in sys.argv:
        del sys.argv[sys.argv.index("db-verbose")]


    if len(sys.argv) <= 1:
        print "halo_db.py can perform the following operations (mutually exclusively on each run):

add <base_dir> - scan under base_dir for timesteps and add them under a new simulation
rem <base_dir> - remove everything relating to simulation identified by base_dir
rollback <run_id1> , <run_id2>, ...
rollback <run_id_first> - <run_id_last_inclusive> [-f] - remove everything added by a particular process (prompts for confirmation)
recent-runs <n> - list n most recent processes which modified the database
deprecate - ensure the deprecation records of all halo properties are consistent
grep-run - find runs with command line matching expression
add-tracker <base_halo> - add a "tracker" halo to the simulation by tracking the DM particles in the centre of the specified existing halo
copy-property <base_halo> <relationship> <property1> <property2> ...
update-trackers - sync all timesteps references to halo trackers (useful after adding more timesteps)
db-import <db> <sim> - import the simulation from the specified db file into the current main db
db-export <db> <sim> - export the simulation from the default db into the mentioned file [NOT IMPLEMENTED]
list-simulations - list all known simulations
"
        sys.exit(0)

    if sys.argv[1] == "list-simulations":
        for x in all_simulations():
            print x.basename

    if sys.argv[1] == "add":
        for sim in sys.argv[2:]:
            add_simulation_timesteps(sim, True)

    if sys.argv[1] == "update-trackers":
        update_tracker_halos(*sys.argv[2:])

    if sys.argv[1] == "rem":
        for sim in sys.argv[2:]:
            rem_simulation_timesteps(sim)

    if sys.argv[1] == "add-tracker":
        add_tracker(*sys.argv[2:])

    if sys.argv[1] == "rollback":
        confirm = True
        if "-f" in sys.argv:
            confirm = False
        if "-" in sys.argv:
            dash = sys.argv.index("-")
            for run_id in xrange(int(sys.argv[dash - 1]), int(sys.argv[dash + 1])):
                rem_run(run_id, confirm)

        for run_id in sys.argv[2:]:
            rem_run(int(run_id),confirm)

    if sys.argv[1] == "recent-runs":
        list_recent_runs(int(sys.argv[2]))

    if sys.argv[1] == "deprecate":
        update_deprecation(internal_session)

    if sys.argv[1] == "update":
        update_simulations()

    if sys.argv[1] == "grep-run":
        grep_run(" ".join(sys.argv[2:]))

    if sys.argv[1] == 'db-import':
        db_import(*sys.argv[2:])

    if sys.argv[1] == 'db-export':
        db_export(*sys.argv[2:])

    if sys.argv[1] == 'copy-property':
        copy_property(*sys.argv[2:])

    """
