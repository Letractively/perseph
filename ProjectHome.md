Persephone is a data abstraction mechanism. Its purpose is to remove all the tedious parts of working with databases and lets you focus on real code. Standard searching, loading, and saving of data to/from databases is handled automatically -- along with protection for data types and incorrect operations. Beyond persistence Persephone can also generate HTML listings and Forms for your data.


Unlike ActiveRecord style systems, Persephone assumes you have a lot of existing code and/or and existing database and have no ability, nor desire, to completely replace it. Thus Persephone operates in a miminally invasive manner, by being very clear about what it is doing, and operating happily alongside alternate solutions. There are no method assumptions, no prescriptive behaviours, and basically nothing that will make curse the solution.


Currently Persephone supports PHP code generation.  Other targets are possible, the source schema language is not PHP specific.