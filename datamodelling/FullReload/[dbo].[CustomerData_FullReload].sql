CREATE TABLE [dbo].[CustomerData_FullReload] 
(
    CustomerData_FullReloadKey INT IDENTITY(1,1),  -- Primary key with auto-increment
    [CustomerID] INT NOT NULL,                    -- Customer ID
    [CustomerName] NVARCHAR(100) NULL,            -- Customer Name
    [Email] NVARCHAR(100) NULL,                   -- Email
    [Phone] NVARCHAR(20) NULL,                    -- Phone
    [City] NVARCHAR(50) NULL,                     -- City
    [LastUpdated] DATETIME NULL,                  -- Last Updated timestamp
    [CreatedAsAt(ETL)] DATETIME NULL,             -- ETL Created timestamp
    [BatchID] INT NULL                            -- Batch ID
)