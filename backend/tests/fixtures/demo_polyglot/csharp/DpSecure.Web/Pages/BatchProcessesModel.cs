using Statements.Core.Batch;

namespace DpSecure.Web.Pages
{
    /// <summary>Lists in-flight batch processes.</summary>
    public class BatchProcessesModel
    {
        private readonly BatchRepository _repo;

        /// <summary>Wires up the repository.</summary>
        public BatchProcessesModel(BatchRepository repo)
        {
            _repo = repo;
        }
    }
}
