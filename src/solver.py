'''
Solver is the abstraction of a constituent solver of the portfolio. Each solver 
must be an object of class Solver.

RunningSolver is instead a solver running on a given FlatZinc model.
'''

import uuid
import psutil
from shutil import move
from string import replace

class Solver:
  """
  Solver is the abstraction of a constituent solver of the portfolio.
  """
  
  # Solver name. It must be an unique identifier.
  name = ''
  # Absolute path of the folder containing solver-specific redefinitions.
  mznlib = ''
  # Absolute path of the command used for executing a FlatZinc model.
  fzn_exec = ''
  # Solver-specific FlatZinc translation of the MiniZinc constraint "LHS < RHS".
  constraint = ''
  # Solver-specific option for printing all the solutions (for CSPs only) or all
  # the sub-optimal solutions (for COPs only).
  all_opt = ''
  # Solver-specific option for free search (i.e., to ignore search annotations).
  free_opt = ''
  
class RunningSolver:
  """
  RunningSolver is the abstraction of a constituent solver running on a given 
  FlatZinc model.
  """
  
  # Object of class Solver, identifying the running solver.
  solver = None
  
  # Status of the solving process. It can be either:
  #     'ready': solver is ready to execute the mzn2fzn conversion
  #   'mzn2fzn': solver is running mzn2fzn converter
  #  'flatzinc': solver is running the FlatZinc interpreter
  # Note that the status is preserved even when a solver process is suspended.
  status = ''
  
  # Don't stop solver if it has produced a solution in the last wait_time sec.
  wait_time = -1
  
  # Restart solver if its best solution is obsolete and it has not produced a 
  # solution in the last restart_time sec.
  restart_time = -1
  
  # Timeout in seconds of the solving process.
  timeout = -1
  
  # Time in seconds (since the epoch) when the solving process started.
  start_time = -1
  
  # Time in seconds (since the epoch) when the solver found its last solution.
  solution_time = -1
  
  # Absolute path of the FlatZinc model on which solver is run.
  fzn_path = ''
  
  # String of the options used by the FlatZinc interpreter of the solver.
  fzn_options = ''
  
  # Dictionary (variable, value) of the best solution currently found by solver.
  solution = {}
  
  # Can be either 'sat', 'min', or 'max' for satisfaction, minimization, or 
  # maximization problems respectively.
  solve = ''
  
  # Objective variable of the FlatZinc model.
  obj_var = ''
  
  # Best objective value found by solver.
  obj_value = None
  
  # Object of class psutil.Popen referring to the solving process.
  process = None
  
  # Auxiliary variable possibly introduced for tracking the objective function 
  # value (that will be printed on std output as a comment).
  aux_var = ''
  
  def __init__(
    self, solver, solve, fzn_path, options, 
    wait_time, restart_time, timeout, aux_var
  ):
    self.status       = 'ready'
    self.solver       = solver
    self.solve        = solve
    if solve == 'min':
      self.obj_value = float('+inf')
    elif solve == 'max':
      self.obj_value = float('-inf')
    self.fzn_path     = fzn_path
    self.fzn_options  = options
    self.wait_time    = wait_time
    self.restart_time = restart_time
    self.timeout      = timeout
    self.aux_var      = aux_var
  
  def name(self):
    """
    Returns the name of the running solver.
    """
    return self.solver.name
  
  def mem_percent(self):
    """
    Returns the memory usage (in percent) of the solver process.
    """
    m = self.process.memory_percent()
    for p in self.process.children(recursive = True):
      try:
        m += p.memory_percent()
      except psutil.NoSuchProcess:
        pass
    return m
  
  def mzn2fzn_cmd(self, pb):
    """
    Returns the command for converting a given MiniZinc model to FlatZinc by 
    using solver-specific redefinitions.
    """
    cmd = 'mzn2fzn --output-ozn-to-file ' + pb.ozn_path + ' -I '     \
        + self.solver.mznlib + ' ' + pb.mzn_path + ' ' + pb.dzn_path \
        + ' -o ' + self.fzn_path
    return cmd.split()
    
  def flatzinc_cmd(self, pb):
    """
    Returns the command for executing the FlatZinc model.
    """
    cmd = self.solver.fzn_exec + ' ' + self.fzn_options + ' ' + self.fzn_path
    return cmd.split()
  
  def set_obj_var(self):
    """
    Retrieve and set the name of the objective variable in the FlatZinc model, 
    which is modified for properly printing the value of such variable.
    """
    lines = []
    # Extract objective variable.
    with open(self.fzn_path, 'r') as infile:  
      for line in reversed(infile.readlines()):
        tokens = line.split()
        if 'solve' in tokens:
          self.obj_var = tokens[-1].replace(';', '')
        lines.append(line)
      infile.close()
    # Adding auxiliary variable in the model.
    with open(self.fzn_path, 'w') as outfile:
      for line in reversed(lines):
        tokens = line.split()
        if tokens[0] == 'var' and (
	  self.obj_var in tokens       or \
	  self.obj_var + ';' in tokens or \
	  self.obj_var + '::' in tokens
	):
	  dom = tokens[1]
	  var = 'var ' + dom + ' ' + self.aux_var + ':: output_var;\n';
	  outfile.write(var)
	if tokens[0] == 'solve':
	  cons = 'constraint int_lin_eq([1, -1], [' \
	       + self.obj_var + ', ' + self.aux_var + '], 0);\n'
	  outfile.write(cons)
	outfile.write(line)
  
  def inject_bound(self, bound):
    """
    Injects a new bound to the FlatZinc model.
    """
    if self.solve == 'min':
      cons = self.solver.constraint.replace(
	'LHS', self.obj_var).replace('RHS', str(bound))
    elif self.solve == 'max':
      cons = self.solver.constraint.replace(
	'RHS', self.obj_var).replace('LHS', str(bound))
    else:
      return
    tmp_path = str(uuid.uuid4())
    with open(self.fzn_path, 'r') as infile:
      with open(tmp_path, 'w') as outfile:
        add = True
        for line in infile:
          if add and 'constraint' in line.split():
            outfile.write(cons + ';\n')
            add = False
          outfile.write(line)
    move(tmp_path, self.fzn_path)
    self.obj_value = bound
