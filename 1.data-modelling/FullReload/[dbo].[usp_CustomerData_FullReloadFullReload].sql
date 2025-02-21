IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'dbo')
BEGIN
    EXEC('CREATE SCHEMA [dbo]');
END
GO

CREATE PROCEDURE [dbo].[usp_CustomerData_FullReloadFullReload]
    @RowsInserted INT OUTPUT,
    @RowsUpdated INT OUTPUT,
    @RowsDeleted INT OUTPUT,
    @BatchID INT
AS
BEGIN
    -- Declare local variables
    DECLARE @CurrentDateTime datetime = CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'New Zealand Standard Time' AS datetime);

    -- Truncate the target table
    TRUNCATE TABLE [dbo].[CustomerData_FullReload];

    -- Insert data from the source table into the target table
    INSERT INTO [dbo].[CustomerData_FullReload] 
        ([CustomerID], [CustomerName], [Email], [Phone], [City], [LastUpdated], [CreatedAsAt(ETL)], [BatchID])
    SELECT 
        [CustomerID], [CustomerName], [Email], [Phone], [City], [LastUpdated], @CurrentDateTime AS [CreatedAsAt(ETL)], @BatchID 
    FROM 
        [Landing].[CustomerData_FullReload];

    -- Set output parameters
    SET @RowsInserted = @@ROWCOUNT;
    SET @RowsUpdated = 0;  -- No updates during a full load
    SET @RowsDeleted = 0;  -- No deletes during a full load

    -- Return the result
    SELECT '[dbo].[CustomerData_FullReload]' AS SourceTableName, @RowsInserted AS RowsInserted, @RowsUpdated AS RowsUpdated, @RowsDeleted AS RowsDeleted;
END;